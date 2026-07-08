# Speaker Script — YourAI RAG QA Knowledge Share
**Audience:** QA Head + QA Team  
**Duration:** ~25 minutes + Q&A  
**Deck:** `YourAI_RAG_QA_Knowledge_Share.pptx` (22 slides — final)

**How to use this:** These are talking points, not a script to read word-for-word. Glance, then say it in your own voice.

---

## Before You Start

- Put your name on slide 1.
- Keep the evaluation report open in a browser tab — just in case.
- One line to remember: *"We use AI to test our RAG chatbot — answer quality, document grounding, prompt compliance — with a 0.70 pass threshold."*
- You're not reading a document. You're explaining something you built. Talk to the room.

---

## SLIDE 1 — Title (~30 sec)

> Hey everyone, thanks for joining.
>
> So today I want to walk you through how we tested YourAI — our legal RAG chatbot — using an AI-powered QA setup. I'll cover why this kind of testing is different from what we're used to, the three-layer model we built with RAGAs, DeepEval, and LLM-as-Judge, and how all of us on the QA side can actually use this going forward.
>
> And honestly — this isn't just a YourAI thing. If we get this right, the same approach works for any document-based AI product we test in the future.

**Tip:** Look at your QA head when you say that last line.

---

## SLIDE 2 — Part 01 (~10 sec)

> Alright, let me start with the problem — why our usual QA approach wasn't enough here.

---

## SLIDE 3 — RAG Changes the QA Equation (~2 min)

> So with a normal chatbot, our job is pretty straightforward — did it respond? Does the answer look okay? We can usually tell by reading it.
>
> YourAI is a different beast. It's RAG — Retrieval-Augmented Generation. When someone asks a question, the system first pulls chunks from uploaded legal documents, and then the LLM builds an answer from those chunks.
>
> And that creates three problems for us as QA:
>
> First — the answer has to be **factually correct**, not just well-written.
>
> Second — it has to come from the **right document**. Not from the model's general knowledge.
>
> Third — this product has **multiple modes** — Legal Q&A, Case Analysis, Document Summarisation — and each one behaves differently.
>
> Now imagine us manually checking fifty document-based answers every sprint. That's not sustainable. We needed something automated — but not just "did the API return 200." We needed automation that actually understands RAG.

**If someone asks — why not just manual testing?**

> Manual testing still has a place — edge cases, UI flows, things you can't automate. But for regression across intents and documents, we need scored, repeatable runs. Otherwise a prompt change or model update can break things and we won't catch it until production.

---

## SLIDE 4 — What Is RAG? (~1.5 min)

> Quick look at this diagram.
>
> User asks a question → system searches the uploaded documents → pulls relevant chunks → LLM generates the answer from those chunks.
>
> So as QA, we're actually validating **two things** — did retrieval find the right paragraphs, and did the model answer correctly based on what it found? That's exactly why our metrics are split into two tiers. You'll see that in a bit.

---

## SLIDE 5 — Part 02 (~10 sec)

> So here's what we built to handle all of this.

---

## SLIDE 6 — AI Testing AI (~1.5 min)

> The way I think about it — **AI testing AI**, but we're still in the driver's seat.
>
> **Our role as QA** — we design the questions, pick the intents, flag edge cases, and make sense of the final report. That's still us. What we *can't* realistically do is sit and write the correct legal answer for every single test case. We're not legal experts, and even if we were — writing fifty ground-truth answers per sprint isn't practical.
>
> That's where the **Generator LLM** comes in. It reads the same uploaded document and writes the reference answer for us. So every question has a correct answer tied to the source doc.
>
> Then the **Judge LLM** scores what the chatbot actually returned — against that ground truth, against the retrieved context, and against the prompt rules. And it does that for every test case, every sprint, automatically.

---

## SLIDE 7 — Three-Layer Model (~2 min)

> **Slow down here — this is important.**
>
> We evaluate in three layers. All three matter.
>
> **Layer 1 — Answer Quality.** RAGAs Tier 1. Did the chatbot say the right thing? Is it relevant, factually correct, close enough to our ground truth?
>
> **Layer 2 — Retrieval & Grounding.** RAGAs Tier 2 plus DeepEval. Did the answer actually come from the document? Did retrieval pull the right chunks? Any hallucination?
>
> **Layer 3 — Product Compliance.** Separate LLM-as-Judge. Does the answer follow the intent's system prompt, tone, and custom instructions?
>
> And here's the thing — RAGAs alone isn't enough. I've seen answers that score well on correctness but use the wrong tone, or cross into legal advice territory. Layer 3 catches that.

**If someone asks — why not one combined score?**

> Because each layer points to a different team and a different fix. Layer 1 is a content issue. Layer 2 is a RAG pipeline issue. Layer 3 is a prompt issue. One number would hide all of that.

---

## SLIDE 8 — Part 03 (~10 sec)

> Now the meat of it — what we actually measure, what the numbers mean, and where we draw the line for pass or fail.

---

## SLIDE 9 — What Is RAGAs? (~1 min)

> RAGAs is an open-source framework built specifically for evaluating RAG apps. Industry standard stuff.
>
> It uses an LLM as the judge — same idea as what we're doing.
>
> Tier 1 is always on — it checks generation quality. Tier 2 kicks in when document context is available — that's retrieval quality. Splitting them like this is exactly what a RAG product needs.

---

## SLIDE 10 — RAGAs Tier 1 (~2.5 min)

> Three metrics here — let me walk through each one.
>
> **Answer Relevancy** — did it actually answer what was asked? Simple example: someone asks about a specific sentence in a court case, and the bot goes off on a general lecture about criminal law. That's a fail.
>
> **Answer Correctness** — are the facts right compared to our ground truth? This is the big one. Wrong charges, wrong dates, wrong ruling — all caught here.
>
> **Answer Similarity** — does it mean the same thing even if the wording is different? Because in legal content, the same answer can be written ten different ways and still be correct.

---

## SLIDE 11 — RAGAs Tier 2 (~2.5 min)

> Tier 2 is about the RAG pipeline itself.
>
> **Faithfulness** — is every claim in the answer actually backed by the retrieved document? This is where we catch hallucination — when the AI sounds really confident but made something up.
>
> **Context Precision** — of everything that was retrieved, how much was actually relevant? Low score means noisy retrieval — wrong sections got pulled in.
>
> **Context Recall** — did retrieval find enough to answer the question fully? Low score here means the bot never had a chance — the key paragraph was missing from what got retrieved.

---

## SLIDE 12 — DeepEval (~2 min)

> We added DeepEval on top because a legal AI product has safety requirements that RAGAs doesn't fully cover.
>
> **Hallucination** — does the answer contradict the source? Important note: this one's **inverted**. Lower is better. Zero means no contradictions at all.
>
> **Non-Advice** — is the bot staying informational? Not crossing into "you should do this" legal advice? For a legal product, this is critical.
>
> **Contextual Relevancy** — kind of complements Context Precision — is the retrieved material actually on-topic for the question?

**If someone asks — why not just RAGAs?**

> RAGAs handles core RAG quality really well. But Non-Advice — legal safety — that's not really covered by standard RAGAs metrics. For what we're building, we needed DeepEval on top.

---

## SLIDE 13 — LLM-as-Judge (~2 min)

> This runs separately from RAGAs.
>
> Each intent in YourAI — General Chat, Legal Q&A, whatever — has three prompt layers: system prompt, tone prompt, and custom instruction.
>
> So for every answer, we run three checks:
> - Did it follow the intent's core instructions?
> - Is the tone professional enough for a legal product?
> - Did it meet format rules and disclaimers?
>
> Real examples we've seen — answer is factually correct but way too casual. Or the required disclaimer is missing. Or it was supposed to use bullet points and didn't.
>
> RAGAs would say "correct answer." Layer 3 says "yeah but it broke the product rules."

---

## SLIDE 14 — Pass / Fail (~1.5 min)

> All scores run from 0 to 1. Our release gate is **0.70 — seventy percent**.
>
> 0.85 and up — excellent.
> 0.70 to 0.84 — pass, good enough for release.
> Below 0.70 — fail, we need to dig in.
>
> A test case only passes if **every active metric** for that case clears the threshold.
>
> One exception — Hallucination is inverted. Lower is better. Zero is perfect.
>
> And we always look at scores **by intent** — Legal Q&A failing means something different from General Chat failing. Different team, different fix.
>
> Long term, once the product stabilises, we'll tighten this to 0.80.

---

## SLIDE 15 — Part 04 (~10 sec)

> Okay, enough theory — let me show you how we actually run this in practice.

---

## SLIDE 16 — Building the Test Dataset (~2 min)

> So the golden rule — ground truth has to come from the **same document** the chatbot has in scope. Otherwise we're comparing apples to oranges.
>
> **We design the questions** — realistic stuff a lawyer would actually ask, tagged by intent and case type.
>
> **AI writes the reference answers** — the LLM reads the document and generates ground truth for us. We spot-check the important ones, but we don't need to manually write every answer. That's the whole point.
>
> Real example from our run — Pennsylvania Superior Court opinion. We asked: "What crimes did the appellant plead guilty to?" Ground truth had seven specific charges from the plea agreement. Then we scored the chatbot's answer against that.
>
> And the whole flow is automated — set up the environment, build the dataset, hit the live API, run scoring, share the report with engineering. Repeat every sprint.

---

## SLIDE 17 — Test Coverage (~1.5 min)

> Every test case sits on two axes.
>
> **Intent** — General Chat, Legal Q&A, Legal Research, Case Analysis, and so on. Each mode has different prompts and different expectations.
>
> **Case type** — Positive questions where we expect a good answer. Negative ones where the bot should refuse. Edge cases with legal nuance. Adversarial stuff trying to break the bot.
>
> One thing to watch — if our negative cases score **high on relevancy**, that's bad. It might mean the bot is actually engaging with harmful requests instead of refusing them.

---

## SLIDE 18 — Part 05 (~10 sec)

> Let me show you what the output actually looks like.

---

## SLIDE 19 — Dashboard (~2.5 min)

> This is real output from our YourAI run — not mock data.
>
> Top banner — red means at least one metric dropped below 0.70 overall.
>
> Score cards — you can instantly see which dimension is weak. No guessing.
>
> The **Scores by Intent** table — this is the one I spend most time on. It tells us which product mode needs attention. Like, Legal Q&A failing on Non-Advice? That's a prompt fix. General Chat failing on Correctness? Different problem entirely.
>
> And if someone asks about all the red — failing scores in early runs are normal. The value is we now have **numbers** to show engineering, not just "hey this feels wrong."
>
> One thing I learned the hard way — if you see **zero across every metric** on a row, don't file a content bug. That's usually an API timeout or empty response. Infrastructure issue, not AI quality. Always check that first.

---

## SLIDE 20 — Part 06 (~10 sec)

> Last section — where we are today and where this goes from here.

---

## SLIDE 21 — Roadmap (~1.5 min)

> **Right now** — we've got automated RAG evaluation working. RAGAs, DeepEval, intent judging — all running.
>
> **Next** — plug this into CI/CD so releases get blocked if scores drop below threshold.
>
> **Scale** — more documents, more intents, dashboards so leadership can see trends.
>
> **Optimise** — tighter thresholds, better adversarial test suites, keeping ground truth fresh.
>
> And on the team side — whether you're on manual or automation, we all use the same framework. Manual side owns question design and reading the report. Automation side owns pipeline integration and regression gates. Same tool, different focus.

---

## SLIDE 22 — Takeaways + Q&A (~1.5 min)

> Let me wrap up with what's on the slide.
>
> RAG chatbots need testing against source documents — not just "does it reply."
> RAGAs is our standard for answer and retrieval quality.
> DeepEval covers the legal safety piece RAGAs misses.
> LLM-as-Judge handles intent, tone, and custom rules.
> 0.70 is our release gate — but read the breakdown, not just the banner.
> And this whole setup works for any RAG product we test in the future.
>
> That's me. Happy to take questions.

---

## IF THEY ASK YOU SOMETHING — Quick Answers

**"How long does a full run take?"**  
> Once it's set up, about thirty to forty-five minutes. Most of that is API calls and judge scoring. If you just want a quick smoke test with five cases, ten minutes.

**"Can we trust AI-generated ground truth?"**  
> We treat it as a strong starting point. We spot-check, especially on edge cases. For straight factual extraction from a document, it's been really consistent. And it's always tied to the source doc text.

**"Can we trust the judge scores?"**  
> RAGAs and DeepEval aren't something we invented — they're industry frameworks. We use GPT-4o-mini as the judge. For regression — catching when things get worse sprint over sprint — it's reliable enough. The trend matters more than any single number.

**"What's the cost?"**  
> Mostly LLM API calls for judging. Few cents per test case. A fifty-case run is usually a couple of dollars.

**"Can other teams use this?"**  
> Absolutely. Same pattern everywhere — ground truth, query the chatbot, score it, report. Swap the document and questions for whatever RAG product you're testing.

**"What do we do when it fails?"**  
> Look at which intent failed, then which metric. That tells you the layer — answer, retrieval, or prompt. File a targeted bug with the score attached. Way more useful than "the AI gave a bad answer."

**"Do we still need manual testing?"**  
> 100%. Automation handles regression at scale. We still need manual for UI flows, exploratory testing, checking refusal behaviour, and reviewing ground truth on critical cases.

**"Why 0.70, not higher?"**  
> It's the industry starting point. Go too high too early and you get false failures from judge variance. Once the product stabilises, we'll move to 0.80.

---

## TIMING

| Section | Slides | Time |
|---------|--------|------|
| Opening | 1 | 0:30 |
| Part 01 — Challenge | 2–4 | 4:00 |
| Part 02 — Framework | 5–7 | 4:00 |
| Part 03 — Metrics | 8–14 | 10:00 |
| Part 04 — How We Test | 15–17 | 3:30 |
| Part 05 — Results | 18–19 | 3:00 |
| Part 06 — Close | 20–22 | 3:30 |
| **Total** | **22** | **~28 min + Q&A** |

Running short on time? Cut slides 16–17 to two minutes total.

---

## DELIVERY REMINDERS

1. **Slides 9–14 are your power moment** — don't rush the metrics.
2. **Point at the dashboard** — "Non-Advice at 0.33 on Legal Q&A — that's a prompt issue, not retrieval."
3. Say **"Layer 1, Layer 2, Layer 3"** — sounds like you know what you're talking about.
4. Say **"we"** not "human QA" or "they" — you're talking to your own team.
5. **If you blank** — look at the slide and say "let me walk you through this." Totally fine.

---

## 30-SECOND VERSION (if they say "summarise it")

> We built an automated QA setup for YourAI's RAG chatbot. We design the test questions, an LLM generates ground-truth answers from uploaded documents, we hit the live API, and then RAGAs scores answer and retrieval quality, DeepEval checks legal safety and hallucination, and a separate LLM judge checks intent and tone compliance. Everything runs against a 0.70 threshold with a pass/fail dashboard. It's repeatable every sprint, works for any RAG product, and gives engineering real numbers instead of us saying "it feels off."
