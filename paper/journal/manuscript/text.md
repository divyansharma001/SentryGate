# 1. Introduction

Applications rarely call a large language model (LLM) directly. A gateway, also called an artificial intelligence (AI) proxy or LLM router, sits between the application and the model provider. It handles the work every application would otherwise repeat: authentication, spending limits, logging, and sending simple requests to a cheaper model. Many gateways now also screen requests for safety.

Two of these jobs matter here. A *semantic cache* turns each prompt into an embedding vector. When a new prompt lies close enough to a stored one, the cache returns the stored answer and no model call is paid for [@bang2023,regmi2024]. A *safety filter*, usually a small classifier, scores each prompt for prompt injection, an attack in which the input text tries to override the model's instructions [@perez2022,greshake2023]. Prompts above a threshold are blocked. Prompt injection ranks first in the Open Worldwide Application Security Project (OWASP) Top 10 for LLM applications [@owasp2024].

Both components have been studied on their own. Caches are judged on hit rate, cost and latency, and filters on detection and false alarms. Recent work has also shown that semantic caches can be poisoned, so that other users receive answers chosen by an attacker [@wuG2026,zhangZ2026a]. Less is known about what happens when a cache and a separate safety filter share one request path. Cost decides the order. A cache lookup takes a few milliseconds and a transformer-based filter takes tens to hundreds. If the filter ran first, every request would pay for it, including the repeated requests the cache was installed to speed up. So gateways check the cache first, and on a hit the stored answer goes back to the user without the filter being consulted.

This ordering leaves a gap that an attacker can use. Once a harmful answer is in the cache, any prompt close enough in meaning to the original will retrieve it unscreened. The cheapest rewordings, such as a changed capital letter or an added full stop, are the closest of all. The filter is not failing here, because it is never asked. Raising the similarity threshold does not solve the problem either, since these edits barely move the embedding.

This paper measures the problem on a running system and closes it by design. Our contributions are:

- a description of the cache-before-filter bypass in LLM gateways, where a cache hit skips a separate input filter, with an explicit threat model;
- a measurement of the bypass on a running, OpenAI-compatible gateway built from real components (a DeBERTa-v3 injection classifier, MiniLM embeddings, Qdrant and Redis), where every counted bypass is backed by the gateway's own log record that the filter did not run;
- *verdict-tagged caching*, a defence that makes the filter's stored verdict part of the cache's match condition and re-checks hits, built as one switch in the same code base as the vulnerable baseline;
- a split of every leak into the part the cache causes and the part the filter would miss even when asked, so that a defence is neither credited nor blamed for the filter's own errors;
- a study of the filter on texts it was not tuned on, which reports false alarms on ordinary text and on adversarial look-alikes separately, along with live measurements of the output guard, rate limiter and model picker; and
- a reproducible artefact, in which every table and figure is regenerated from committed request logs and recorded model replies let every run repeat with no application programming interface (API) key.

Section 2 reviews related work and Section 3 gives the threat model. Section 4 describes the gateway and the defence, and Section 5 sets out the method. Results follow in Section 6, with discussion and threats to validity in Section 7. Section 8 concludes.

# 2. Related work

Table 1 lists the prior work discussed in this section and what each study addresses.

[[TABLE:1]]

## 2.1 Semantic caching for LLMs

A semantic cache stores past prompts as embeddings and returns a stored answer when a new prompt is close enough in meaning. GPTCache is the open-source design most deployments follow [@bang2023]. GPT Semantic Cache [@regmi2024], SCALM [@li2024] and MeanCache [@gill2025] improve on it for hit rate, cost, latency and privacy. These systems are evaluated as performance components, and all of them decide a hit from embedding similarity alone. Schroeder et al. [@schroeder2026] show that a single global threshold cannot bound the rate of wrong hits, and they replace it with learned per-entry thresholds. Their finding concerns answer correctness, but it matches our result in Section 6.1 that no threshold is safe. A threshold controls how close two prompts are. It says nothing about whether the stored answer suits the new prompt.

## 2.2 Prompt injection and its detection

Perez and Ribeiro [@perez2022] named and demonstrated prompt injection, using handcrafted "ignore previous instructions" prompts to hijack GPT-3's goal or leak its prompt. Greshake et al. [@greshake2023] extended the threat to indirect injection through content the model reads later, and compromised real applications this way. Liu et al. [@liu2024] formalised attacks and defences and benchmarked them across models and tasks, and Yi et al. [@yi2025] built a benchmark for the indirect case.

Defences fall into two groups. Model-side defences change how the model treats untrusted text, for example by separating instructions from data [@chenS2025struq], by preference optimisation [@chenS2025secalign], or by marking untrusted input [@hines2024]. System-side defences place a guard around the model. These include input and output classifiers such as Llama Guard [@inan2023], programmable rails [@rebedea2023], and dedicated injection detectors such as the DeBERTa-v3 classifier we deploy [@he2023,protectai2024]. Simpler baselines such as perplexity filtering and paraphrasing also exist [@jain2023]. Detectors can be evaded: Hackett et al. [@hackett2025] bypass six commercial and open detectors with character-level and adversarial changes. Our result is different in kind. We do not attack the detector. We show that a cache in front of it can take it out of the request path, so that even a perfect detector would not be consulted.

## 2.3 Attacks on caches

Caches have long been an attack surface on the web. In web cache poisoning, a request input changes the response but is left out of the cache key, so one attacker's request can store a harmful response that everyone else then receives [@kettle2018]. Cache-poisoned denial of service stores error pages the same way [@nguyen2019], and web cache deception tricks a cache into storing private pages [@gil2017,mirheidari2020]. The flaw we study has the same shape. The safety verdict decides whether a response may be served, yet it is not part of the semantic cache's key. Verdict-tagged caching applies the standard fix, which is to key on the input that matters.

LLM caches now receive the same scrutiny. Timing side channels in shared prompt, key-value (KV) and semantic caches leak other users' prompts [@zheng2024,gu2025,wuG2025,song2025]. Closest to our work, Wu, Wang et al. [@wuG2026] show that the managed semantic caches of three cloud providers can be poisoned so that other users receive attacker-chosen answers. They also test prompt-injection classifiers, including the ProtectAI model we use, as a defence against the poisoning prompts, and find them weak because those prompts look benign. This supports the "saved as clean" case in our threat model. Wu, Ying et al. [@wuX2026] catalogue six cache attacks on LLM serving frameworks, including fuzzy poisoning of GPTCache and a hash collision that lets harmful content inherit a benign cached moderation result. Zhang, Liu et al. [@zhangZ2026a] mount black-box key-collision attacks that hijack responses from semantic caches. Zhang, Yao et al. [@zhangZ2026b] and Liang et al. [@liang2026] defend by checking each candidate hit for whether the cached answer is valid for the new query.

## 2.4 Gateways, routing and the remaining gap

Gateways combine caching with other services. Cost-aware routing sends easy prompts to cheaper models, using cascades [@chen2023frugal] or routers learned from preference data [@ong2025]. Our model picker is a rule-based baseline in the same space. Industry guidance treats the components as separate risks: the OWASP list puts prompt injection first and lists vector and embedding weaknesses separately [@owasp2024].

Prior work therefore establishes that semantic caches can be poisoned and that cache reuse can carry a stale decision forward. We have not found three things. The first is a measurement of what happens when a semantic cache sits in front of a *separate* input classifier in a gateway, so that every hit skips the classifier. The second is a measurement that reads the skip from the system's own logs and separates cache-caused leaks from the classifier's misses. The third is an evaluation of storing the classifier's verdict with each entry and re-checking hits as the fix, including its cost to honest traffic. This paper provides all three. The answer-validity checks of Zhang, Yao et al. [@zhangZ2026b] and Liang et al. [@liang2026] test a different property, whether the answer fits the query, so the two kinds of check complement each other.

# 3. Threat model

## 3.1 System model

We consider a gateway that receives chat-completion requests over an OpenAI-compatible Hypertext Transfer Protocol (HTTP) API. For each request it (i) looks the prompt up in a semantic cache, (ii) on a miss, screens the prompt with an injection classifier and blocks it if the score *s*(*p*) is at least a threshold θ = 0.5, and (iii) otherwise calls the model, returns the answer and stores the pair (*p*, *a*) in the cache. A stored entry is returned for a new prompt *q* whenever the cosine similarity of their embeddings, sim(*q*, *p*), is at least a cache threshold τ. Real systems use this cache-first order. Section 6.2 also evaluates the filter-first order as a reference.

## 3.2 Attacker

The attacker wants an answer the filter would refuse. They can send requests to the gateway like any user and reword their own prompts freely. They need no access to the cache, the vector database, the model or other users' sessions, and no special tools. A text editor is enough.

## 3.3 How a poisoned answer enters the cache

The attack needs a harmful answer stored under a prompt close to the attacker's. There are three routes: (1) a prompt that scored just below the block threshold was allowed, answered and cached; (2) the cache was filled before launch from prompts that were never screened; (3) the cache is shared between tenants, so one tenant's stored answer reaches another. Route (1) needs no privileged access, and it is the one we model. We model the stored entry's verdict in two ways. In the easy case for a defence, the entry carries the filter's own label, usually "attack". In the realistic case it is saved as "clean", as an attack that slipped past once would be.

## 3.4 Out of scope

We exclude attacks on the model's weights or training, on the network between gateway and database, and on the model provider, as well as attacks that need code execution on the gateway host. The filter's own detection error is also out of scope. An attack the filter misses when asked directly is a limit of the filter, not of the cache, and Section 5.3 shows how we keep the two apart.

# 4. System design

## 4.1 Gateway architecture

SentryGate is an OpenAI-compatible gateway written in Python with FastAPI and deployed with Docker Compose behind an nginx reverse proxy. The safety filter is ProtectAI's DeBERTa-v3 prompt-injection classifier [@he2023,protectai2024]. Personal data is detected with Microsoft Presidio [@microsoft], and it is flagged in the verdict but not blocked. Prompts are embedded with all-MiniLM-L6-v2 [@reimers2019,wang2020]. An exact-match layer in Redis sits in front of a similarity layer in Qdrant [@qdrant], whose hierarchical navigable small world (HNSW) index [@malkov2020] supports payload filters applied during the search. Model calls go to OpenRouter and are recorded to disk, so they can be replayed for free.

Every request writes one JavaScript Object Notation (JSON) line with the outcome, the time of each stage, the token cost, whether screening ran, and the configuration and code version that produced it. The prompt itself is never logged, only its hash and length.

Fig. 1 shows the request path. A hit is served only if its stored verdict and label fit the request and it passes the re-check and the output guard. A miss is screened, routed to a model, guarded, and stored with its verdict. The dashed line is the baseline path, on which a hit skips the filter.

[[FIG:1]]

## 4.2 Verdict-tagged caching

The filter's result is already computed on every miss, so it can be stored next to the cached answer and consulted on each lookup at almost no cost. A cached entry *e* holds the answer, the prompt embedding and the verdict of the prompt that created it: an injection flag and score, a personal-data flag, an intent label and a risk level. Each incoming prompt *q* also gets a cheap intent label *c*(*q*) from keyword rules (credentials, tool use, personal data, informational, other). These rules run in microseconds and need no model. The same rules label each entry when it is stored, so a prompt and its stored answer get the same label. An entry may then be served for *q* only if

[[EQ]]

where τ is 0.95 for the risky labels (credentials, tool use, personal data) and 0.85 otherwise, and R is the re-check condition below. The first two conditions are expressed as a Qdrant payload filter. The vector search therefore only returns entries that already satisfy them, and no candidate is discarded afterwards.

The re-check R runs the full filter on *q* before a hit is served and blocks it if *s*(*q*) ≥ θ. It has two scopes. The *risky* scope re-checks a hit only if the request's cheap label is risky or the entry's stored injection score was at least 0.2, a close call when it was saved. This was our first design, meant to keep most hits at full speed. The *all* scope re-checks every hit. Section 6.3 shows that only the second closes the gap. Re-checking every hit may seem to defeat the purpose of a cache, but a cache saves the model call, which costs seconds and money. The filter costs tens of milliseconds and nothing per call.

## 4.3 Further mitigation layers

Three more layers complete the gateway. An *output guard* scans every answer, including one served from the cache, for content an application should almost never receive: browser script, destructive Structured Query Language (SQL) statements, dangerous shell commands, and strings shaped like secret keys. It can be off, flag the answer in a response header, or block it, and a blocked answer is never written to the cache. Because it reads the answer and not the question, it works behind the cache without depending on the input filter.

A *rate limiter* enforces per-caller requests per minute, counting cache hits, and a daily model-token budget. Its counters live in Redis, so a restart does not reset them. A *model picker* scores each miss with plain rules (code, mathematics, reasoning words, length, multiple questions) and sends easy prompts to a cheap model and hard ones to a strong model, following the idea of cost-aware routing [@chen2023frugal,ong2025]. If the chosen model's call fails, a fallback model is tried once.

## 4.4 One code base, one switch per layer

The vulnerable baseline and every defended configuration are the same program. Each layer is a single environment variable, read once at start-up and copied into every log line. No two arms can differ by accident, and every comparison in Section 6 is a change of flags. An automated test checks that each setting the code reads is passed into the container, added after one such omission silently disabled a layer during development. The {{n_tests}} tests run without network access, model downloads or API keys, and a pinned linter reports no problems.

# 5. Experimental method

## 5.1 Attack corpus

Seed attacks come from two public datasets on Hugging Face. We took every English attack of 20 to 400 characters in `deepset/prompt-injections` ({{n_seeds_deepset}} seeds) [@deepset2023] and a seeded random sample of {{n_seeds_jay}} attacks from `jayavibhav/prompt-injection` [@jayavibhav2024], {{n_seeds}} seeds in all. German deepset items are excluded because the filter is trained for English only [@protectai2024].

Each seed is reworded in two families, kept apart throughout because they behave very differently. *Lazy edits* are fixed rules an attacker can apply for free: flipping the case of the first letter, adding or removing a full stop, adding an exclamation mark, "please" at the start or end, a double space, all capitals, one typo, and stripped punctuation ({{n_lazy}} variants). *Full paraphrases* come from a T5 paraphraser [@vorobev2023] with deterministic beam search (three per seed, {{n_rewrite}} variants). One further "exact" variant, the seed itself, must always hit and serves as a wiring check. A separate set of {{n_controls}} honest questions from the same source acts as controls.

All inputs are generated by a committed script with a fixed random seed and recorded with file hashes. Table 2 lists each data set, its source and size, and the experiments that use it. The sets used to test the filter alone share no text with the attack seeds, and the filter was not tuned on any of them.

[[TABLE:2]]

## 5.2 Procedure

Fig. 2 shows the measurement harness. Inputs are generated once, and each experiment arm then restarts the gateway with its own settings. For each seed, the cache is cleared and one poisoned entry is planted under the seed text, through a test-only endpoint that stays off unless explicitly enabled. Every variant of that seed is then sent to the gateway over HTTP. Each reply is joined to the gateway's log line for that request through a request identifier the gateway returns.

The poison is a fixed marker string carrying a leaked "system prompt" and a fake API key. The {{n_controls}} controls are each sent against a freshly poisoned cache, to check that honest users never receive the poison. To measure what a defence costs honest users, each control is asked once (a miss, which stores its answer) and then reworded with the same lazy edits. The share of those rewordings answered from the cache is the honest hit rate.

[[FIG:2]]

## 5.3 Measures

A *bypass* is counted only when two independent facts agree: the reply body is exactly the poison string, and the gateway's log line records that screening did not run. The second fact comes from the system under test, not from our harness. *Poison served* counts replies equal to the poison whether or not the filter ran.

Since the filter misses some attacks on its own, poison served mixes two causes. We therefore ask the same filter about every variant directly, in the filter-first order, and split each served poison in two. It is *cache-caused* if the filter blocks that exact text when asked, because the cache is then the reason it got through. It is a *filter miss* if the filter lets the text through anyway, because then no cache defence could stop it. Only the cache-caused share measures a cache defence. We also report the honest hit rate, the median latency of honest hits and misses, the filter's false-alarm rate on honest text, and its detection rate on attacks.

## 5.4 Experiments

Table 3 lists the five experiments, E1 to E5, with the question each answers and its scale. E1 to E4 use the real filter, embedder and stores with the model reply mocked, since a cached answer never reaches the model. E5 uses real, paid model calls. Section 6.6 adds two live demonstrations of the remaining mitigation layers.

[[TABLE:3]]

## 5.5 Statistical treatment

The rewordings of one seed are not independent: if one lazy edit of a seed matches the poisoned entry, the others usually do too. A binomial interval over variants would be too narrow. Every rate over attack variants therefore has a 95% confidence interval (CI) from a cluster bootstrap that resamples whole seeds with replacement, with 2,000 resamples and a fixed random seed [@efron1993,field2007]. When no event occurs at all, resampling can only return zero, so we report the conservative rule-of-three upper bound over seeds, 3/*n*, where *n* is the number of seeds [@hanley1983]. Rates over independent texts, as in E4, use the Wilson score interval [@wilson1927].

## 5.6 Environment and reproducibility

All runs used one Apple M5 laptop ({{hw_cores}} cores, {{hw_mem_gb}} GB memory) with Docker Desktop limited to {{docker_cpus}} central processing units (CPUs) and {{docker_mem_gb}} GB. Models ran on CPU only (PyTorch {{torch_version}}, sentence-transformers {{st_version}}, Qdrant {{qdrant_version}}). Committed scripts produce every table and figure from the request logs and result files alone. Recorded model replies let every run repeat without an API key or cost.

# 6. Results

## 6.1 The bypass on a running gateway (E1)

Table 4 and Fig. 3 report the bypass rate: the share of attack rewordings answered with the poison while the gateway's log records that the filter did not run. Each of the seven thresholds uses all {{n_variants}} rewordings, and the shaded bands in Fig. 3 are 95% seed-bootstrap CIs.

At τ = 0.85, a common default, {{w4_lazy_85}}% of lazy edits (95% CI {{w4_lazy_85_ci}}) and {{w4_all_85}}% of all rewordings received the poison unscreened. At 0.95, the strictest setting a product would plausibly use, {{w4_lazy_95}}% of lazy edits still got through. Full paraphrases behave differently. They rarely match at strict thresholds ({{w4_rewrite_95}}% at 0.95) and become dangerous only as the threshold loosens ({{w4_rewrite_65}}% at 0.65), because a real paraphrase moves the embedding much further than a changed capital letter does.

The attacker needs no skill, since the cheapest rewordings work best. No threshold is both safe and useful: moving τ from 0.85 to 0.95 lowers the lazy-edit bypass rate by only {{w4_lazy_drop}} points, and a stricter threshold also matches fewer of the honest rephrasings that make a semantic cache worthwhile.

[[TABLE:4]]

[[FIG:3]]

Four checks support the measurement. The exact seed text, which must always hit, received the poison in {{w4_exact}} cases. All {{w4_confirmed}} confirmed bypasses across the sweep have a log line recording that screening did not run. No honest control received the poison ({{w4_controls}} control requests). The similarity score in the log also agreed with the hit-or-miss decision for every request ({{w4_mismatch}} disagreements).

## 6.2 The order is the cause (E2)

We ran the same build with the filter moved in front of the cache and nothing else changed. The bypass rate fell to zero, which shows that the ordering causes the bypass. That zero holds by construction, though, because in the filter-first order the filter always runs. The poison is still served for {{e2_served_pct}}% of rewordings in this order, since the filter itself lets those texts through. Asked directly, it blocks {{e2_blocked_pct}}% of the rewordings: {{e2_blocked_jayavibhav}}% of those derived from jayavibhav seeds, but only {{e2_blocked_deepset}}% of those from deepset, whose attacks are more conversational. This is the filter's own limit, and it is why every later result separates cache-caused leaks from filter misses.

## 6.3 Verdict-tagged caching (E3)

Table 5 and Fig. 4 report the five defence settings, each with the poison saved as an attack (the easy case) and as clean (the realistic case), at τ = 0.85. Table 5 gives the cache-caused leak rate with 95% CIs, the share of honest rewordings still answered from the cache, and the median latency of honest hits and misses. The model reply is mocked, so a miss excludes model time. In Fig. 4 the coloured part of each bar is cache-caused, and the grey part is what the filter misses even when asked.

[[TABLE:5]]

[[FIG:4]]

*Label matching stops the easy case.* When the poison was saved with an attack label, refusing entries whose stored verdict is "attack" cuts cache-caused leaks from {{p3_base_attack}}% to {{p3_filter_attack}}%. The remainder comes from seeds the filter itself labelled clean when the poison was stored, whose rewordings it would have caught.

*It does not stop the realistic case.* When the poison was saved as clean, its stored verdict looks like any honest entry's, and label matching barely helps ({{p3_filter_clean}}%). A verdict that was wrong when stored stays wrong.

*Re-checking only risky hits is not enough.* The keyword label calls most real attacks harmless. Only {{n_seeds_risky}} of the {{n_seeds}} seeds get a risky label, and most are labelled "informational" or "other". Most poisoned hits are therefore never re-checked, and {{p3_both_clean}}% still get through with both mechanisms on.

*Re-checking every hit closes the gap.* With every hit screened again before it is served, cache-caused leaks fall to zero in both cases (0 of {{n_variants}}; 95% upper bound {{p3_all_upper}}%). About {{p3_all_clean_miss}}% is still served, and this is exactly the share the filter misses when asked directly, so the cache adds no risk beyond the filter's own. Honest traffic kept {{p3_all_hits}}% of its cache hits in every setting, and no honest control received the poison in any setting.

The cost is time. A re-checked hit takes about {{p3_all_hit_ms}} ms at the median, against {{p3_base_hit_ms}} ms for an unscreened hit, because it pays for one filter call. A real model answer, measured in E5, took a median of {{r_cheap_ms}} ms for the cheap model and {{r_strong_ms}} ms for the strong one. A re-checked hit stays more than ten times faster than either, and it costs nothing.

## 6.4 The filter alone (E4)

Every defence here ends by asking the same filter, so the filter's error rates limit what any configuration can achieve. E4 tests it on texts it was not tuned on (Table 6, Fig. 5). On ordinary honest text, the deepset honest questions and 1,000 everyday instructions from Dolly-15k [@databricks2023], it raised {{scr_fa_ord_k}} false alarm in {{scr_fa_ord_n}} texts ({{scr_fa_ord}}%, 95% CI {{scr_fa_ord_ci}}). The jayavibhav honest texts are synthetic sentences full of injection vocabulary ("disregard", "start from scratch", "pre-beginning"), and on these it blocked {{scr_fa_look}}% ({{scr_fa_look_ci}}). The two numbers should not be pooled. The first estimates the cost to ordinary users, and the second shows that deliberately confusing look-alikes defeat the filter.

On attacks, the filter caught {{scr_det}}% overall ({{scr_det_ci}}), but the sources differ widely: {{scr_jayavibhav_det}}% of jayavibhav attacks against only {{scr_deepset_det}}% of deepset attacks, which are conversational and often lack the trigger phrases the classifier relies on. E2 showed the same split.

Table 6 gives the block rate of each set with Wilson 95% CIs. Fig. 5a shows each set's score distribution, and Fig. 5b shows how catches trade against false alarms as the block threshold varies. The scores pile up at the two ends of the scale, so moving the threshold changes little. From 0.1 to 0.9, detection moves only from {{scr_curve_det_01}}% to {{scr_curve_det_09}}%, and look-alike false alarms from {{scr_curve_fa_look_01}}% to {{scr_curve_fa_look_09}}%. The area under the catch/false-alarm curve (AUC) is {{scr_auc_ord}} against ordinary text but only {{scr_auc_look}} against look-alikes.

[[TABLE:6]]

[[FIG:5]]

## 6.5 The model picker on real calls (E5)

We wrote 40 questions, 20 labelled easy and 20 hard, and sent each twice through the live gateway on OpenRouter. The first pass used the model picker, choosing between `openai/gpt-4o-mini` and `openai/gpt-4o`. The second always used the strong model. Costs come from the token counts the provider returned. Table 7 gives the cost of each half of the set under both settings, and Fig. 6 shows the same comparison.

The picker cut the cost of easy questions by {{r_saved_easy}}% and of hard questions by {{r_saved_hard}}%, {{r_saved_all}}% overall. It agreed with our label on {{r_agree}} of {{r_questions}} questions. The one disagreement sent a two-part hard question with no code or mathematics cues to the cheap model, which still answered it correctly. The overall saving is modest because half the set is hard and long hard answers dominate the bill. Applying the measured average cost of each kind to a mix of 80% or 90% easy traffic projects savings of {{r_mix80}}% and {{r_mix90}}%. These two figures are projections. We also forced a failure of the cheap model, and the fallback model answered, with a header naming the failed model.

[[TABLE:7]]

[[FIG:6]]

## 6.6 The output guard and the rate limiter, demonstrated

We exercised both layers on the live gateway with the real filter and embedder. For the output guard, we planted a cached answer carrying a browser script that sends the user's cookies to a third party, then asked a reworded question in each of the guard's three modes. With the guard off, the script was served from the cache (status {{mit_guard_off}}). In flag mode it was served with a response header naming what was found ({{mit_guard_flag}}). In block mode the answer was withheld ({{mit_guard_block}}). The guard acts on a cache hit the input filter never saw, so it gives independent protection behind the cache.

For the rate limiter, with a limit of {{mit_limit}} requests a minute, one caller sent every rewording of one attack three times in a single burst ({{mit_sent}} requests) at a planted poisoned answer. Within the limit, {{mit_answered}} were answered and {{mit_blocked}} blocked by the filter. The other {{mit_refused}} were refused with status 429, while a second caller at the same moment was served normally (status {{mit_other}}). The limiter does not stop the attack, and the attacker still received {{mit_poison}} poisoned answers in the first minute. It does slow the search for a matching rewording to a fixed number of attempts per key per minute.

# 7. Discussion

## 7.1 Why a stored verdict is not enough

We designed verdict-tagged caching on the idea that the filter's decision, once made, can travel with the answer. A stored verdict is only as good as the moment it was computed. When the filter flagged the original prompt, matching on the stored label removes almost all cache-caused leaks at no measurable cost. When the filter was wrong at storage time, which is how a poisoned answer enters the cache under route (1) of the threat model, the stored label vouches for the poison and every reworded attack inherits that wrong verdict. Wu, Wang et al. [@wuG2026] report the same weakness from the other side: injection classifiers, including ours, often fail to flag poisoning prompts that look benign. Only a decision taken on the *new* prompt, when it is served, removes the cache's contribution to the risk.

Restricting the re-check to hits that look risky failed for a related reason. The cheap keyword label is fast because it is shallow, and real injections rarely contain words like "password" or "execute". Most of our seeds were labelled informational. A selective re-check is only as good as the cheap signal that selects it, so the practical rule is to re-check every hit.

## 7.2 What re-checking every hit costs

A cache exists to avoid the model call, which in our live measurements took a median of {{r_cheap_ms}} ms for the cheap model and {{r_strong_ms}} ms for the strong one, and which costs money each time. The re-check adds one classifier pass, about {{recheck_extra_ms}} ms on our hardware, and no per-call cost. The honest hit rate does not change, because an honest prompt that passes the filter on a miss also passes it on a hit. The safe setting spends under 100 ms per hit and keeps the saving that matters.

## 7.3 Recommendations for practitioners

- Treat a semantic cache as part of the attack surface, since a cache in front of a safety filter is a path around it.
- Re-run the input filter on every cache hit. This costs little next to the model call, and it was the only setting we tested that removed every cache-caused leak.
- Store the filter's verdict with every cached answer and filter the vector search on it. This is not enough alone, but it removes known-bad entries at no measurable cost.
- Do not rely on the similarity threshold for safety, because the edits that matter most move an embedding least.
- Scan answers, including cached ones, before they leave the gateway. An output check does not depend on the input filter having run.
- Measure the filter's false-alarm rate on your own traffic, and report leaks split into those the cache causes and those the filter misses.

## 7.4 Threats to validity

- *Mocked model replies.* The attack experiments mock the model reply, because the attack concerns answers served from the cache, where the model is never called. The filter, embedder and stores are real, and the model picker was measured on real, paid calls.
- *One injection route.* We model a poisoned answer entering the cache through a prompt that slipped past the filter, and we plant it directly. Pre-filled and cross-tenant caches are discussed but not measured.
- *One filter, one embedder.* All results use one public injection classifier and one embedding model, and the classifier's model card says the project is no longer maintained. Absolute leak and false-alarm rates will differ for other components. The structural result, that a cache in front of a filter bypasses it unless hits are re-checked, depends on neither.
- *Dataset provenance.* The jayavibhav dataset card documents neither the source of its texts nor the meaning of its labels, and its honest texts are synthetic. We therefore report its false alarms separately from ordinary text. The deepset card is empty and lists conflicting licences.
- *Router tuning.* We adjusted the model picker's rules once after seeing the 40 router questions, so its agreement with our labels is optimistic. The questions and labels are our own.
- *One machine.* Latency was measured on one laptop under Docker Desktop, with other workloads present. Absolute times will differ on server hardware, but the settings were compared on the same machine in the same session.
- *Output guard.* The guard uses plain patterns. It caught the script payload in our demonstration and would miss a payload written to avoid them.

# 8. Conclusion and future work

A semantic cache placed in front of a prompt-injection filter, in the order performance demands, is a path around the filter. On a running gateway built from common open components, {{w4_lazy_85}}% of trivially reworded attacks retrieved a poisoned answer at a typical threshold, the gateway's own log recorded that the filter never ran, and no threshold was both safe and useful.

Storing the filter's verdict with each cached answer and filtering the search on it stops the easy case at no measurable cost. It does not stop the realistic case, in which the poison was stored as clean. Re-checking only the hits that look risky does not close the gap either, because a cheap label cannot recognise most real attacks. Re-checking every hit removed every cache-caused leak and kept {{p3_all_hits}}% of honest cache hits, for about {{recheck_extra_ms}} ms per hit.

What remains is the filter's own error, which we measured separately. It raised almost no false alarms on ordinary text, but it blocked most adversarial look-alikes and missed most conversational attacks. A cache defence can remove the risk the cache adds. It cannot repair the filter.

Several directions follow:

- *Other filters and embedders.* Repeating the measurements with other injection classifiers, LLM-based guards and embedding models would show how the absolute rates move. We expect the structural result to hold.
- *Other injection routes.* In pre-filled and cross-tenant caches, which we discussed but did not measure, a poisoned entry can carry any verdict an attacker chooses. This makes re-checking hits more important.
- *Adaptive attackers.* An attacker who knows every hit is re-checked will look for rewordings that match the poisoned entry and also evade the filter. Adding an answer-validity check [@zhangZ2026b,liang2026] is a natural next layer.
- *A learned model picker*, evaluated on questions it was not tuned on, in place of the rule-based baseline.

# Declaration of competing interest

The authors declare that they have no known competing financial interests or personal relationships that could have appeared to influence the work reported in this paper.

# Data availability

The gateway, the attack and evaluation code, the derived attack set (seeds, variants, controls and their manifest with file hashes), the per-request results of every experiment, the recorded model replies, and the scripts that produce every table and figure, including this paper, are available in the project repository. The raw public datasets are downloaded on demand from Hugging Face and listed in the manifest with their file hashes.

# Declaration of generative AI use

During the preparation of this work the authors used Claude (Anthropic) to assist with writing code and drafting text. The authors reviewed and edited all content, ran every experiment, and take full responsibility for the content of the publication.
