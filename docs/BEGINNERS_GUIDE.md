# Oluso explained for beginners

This document explains what this project is, how it works, and what you would need to learn to
be comfortable with every part of it. It assumes **no machine-learning background at all**.
Everything else in `docs/` is written for engineers and judges; this file is written for a person.

---

## 1. The one-paragraph version

Oluso watches money leaving a bank account and asks one question: *does this look like the real
customer, or like somebody who has stolen their account?* It learns each customer's normal habits,
compares every new payment against those habits, and gives the payment a risk score between 0 and 1.
If the score is low, the money moves. If the score is high, the system does something **reversible**
— watch it, ask the customer to confirm, delay the settlement, or hold it for a human to review.
It never permanently blocks anybody, and it always writes down, in plain English, why it did what
it did.

---

## 2. The problem it is solving

**Account takeover (ATO)** is when a criminal gets into someone else's bank account and moves their
money. It is different from card fraud: the transaction comes from a legitimate account, with a
legitimate PIN, through a legitimate channel. Nothing is technically "invalid". The only thing
that is wrong is that *the person pressing the buttons is not the owner*.

This project targets Nigerian mobile money, which has three ways in:

| Channel | What it means | Why it matters here |
|---|---|---|
| **App** | A smartphone banking app | Rich signals: device ID, typing speed, how the phone is held |
| **USSD** | Dialling codes like `*737#` on any phone, even a cheap one with no internet | Very few signals: no device fingerprint, no typing data. Most Nigerians use this |
| **Agent banking** | A human agent with a terminal in a market or kiosk who does the transaction for you | The *agent's terminal* can be the thing that is compromised, not the customer |

A common attack chain looks like this: the criminal convinces a telecom operator to move the
victim's phone number to a new SIM card (**SIM swap**), receives the victim's one-time passwords,
resets the banking PIN, and drains the balance to a fresh recipient account, which immediately
cashes out. Oluso is built to notice that whole sequence, not just the final transfer.

---

## 3. The core idea: a behavioural twin

For every customer, the system keeps a **behavioural twin** — a statistical summary of how that
person normally banks:

- how much they usually send (the typical amount, and how much it varies)
- what hours of the day they transact
- which recipients, devices, SIM cards and locations they have used before
- how fast they move through app screens or USSD menus
- whether they have a monthly rhythm, like rent on the 28th

The twin is built **only from the customer's own past events**, and it is calculated on the server.
A caller cannot send in their own averages and lie about what is normal for them. That matters:
if an attacker could declare "₦500,000 is normal for this account", the whole system collapses.

A new payment is then compared to the twin. The output is not "fraud / not fraud"; it is a set of
numbers describing *how unusual this is*, and those numbers feed the scoring.

---

## 4. Follow one payment through the system

Take the demo case: a SIM-swap balance drain on USSD.

1. **The event arrives.** The bank's system posts the transaction to the API endpoint
   `POST /v1/events/score`: account, time, amount, balance before, recipient, device, SIM, IP,
   rough location, how long the person spent in the USSD menu.

2. **Features are calculated.** The `FeatureEngine` (`src/oluso/features.py`) turns that raw event
   into roughly sixty numbers by comparing it to the customer's history *before* this event. A few
   examples:
   - `amount_deviation`: how far the amount is from the customer's usual amount
   - `balance_drain_ratio`: 0.92 means this payment takes 92% of what is in the account
   - `new_sim`: 1 if this SIM has never been seen on this account
   - `recipient_rapid_cashout_ratio_1h`: how quickly money sent to this recipient is being emptied out
   - `failed_auth_24h`: failed login attempts in the last day
   - `impossible_travel`: whether the implied travel speed since the last event is physically impossible

3. **Two scorers look at those numbers, separately.**
   - The **population model** — the machine-learning part — gives a probability that this pattern
     resembles a takeover, learned from thousands of past examples.
   - The **anomaly scorer** — a transparent, hand-written rulebook in `src/oluso/scoring.py` — adds
     up weighted points for each unusual signal. A new SIM is worth 0.11, a huge balance drain 0.09,
     a known fraudulent recipient 0.13, and so on.

4. **The two scores are blended.** If the customer's history is thin, the model gets 68% of the
   weight; once the twin is mature, the model drops to 58% and the personal rulebook counts for more.

5. **Security floors can raise the score.** Fifteen named rules cover combinations that are alarming
   regardless of what the model thinks — for example, *new device and new SIM at the same time*, or
   *PIN recovery followed immediately by a transfer to a brand-new recipient*. Each floor sets a
   minimum score. The final score is whichever is higher: the blend, or the highest floor that fired.

6. **Confidence is calculated separately from risk.** This is one of the more thoughtful parts of the
   design. "Low risk" and "we don't know" are not the same thing. A brand-new customer with no
   history gets a low risk score, but the confidence envelope says the evidence is thin, so the system
   does not present it as "known safe".

7. **The policy engine picks an action.** Thresholds on the final score (`src/oluso/policy.py`)
   decide what is allowed to happen:

   | Score | Response |
   |---|---|
   | below 0.30 | allow, possibly with quiet monitoring |
   | 0.30 – 0.48 | monitor, or ask for a step-up confirmation |
   | 0.48 – 0.66 | confirmation, or a reversible delay |
   | 0.66 – 0.84 | delay or hold |
   | 0.84 and above | two-hour hold plus analyst review |

   Within each band it weighs the expected loss from letting fraud through against the *cost to the
   customer* of interrupting them. A USSD confirmation is treated as more annoying than an app one,
   because it is. A payment that looks like an established monthly bill gets more benefit of the
   doubt. And a **regret budget** limits how many times one customer can be disrupted in 30 days,
   so a false-alarm-prone account is not harassed — though genuinely critical cases can override it.

8. **The decision is explained and recorded.** The response includes reason codes, one plain-English
   sentence for the customer, and **recourse**: what they can do to clear it and how long it will take.
   The decision is appended to a SHA-256 hash chain (`src/oluso/audit.py`) so that any later
   tampering with the record is detectable.

9. **Learning is firewalled.** A suspicious event is stored for investigation but is **not** allowed
   to update the trusted baseline for 24 hours. Otherwise an attacker could slowly teach the twin
   that their behaviour is normal — a real attack technique against adaptive systems.

---

## 5. The machine learning part, from zero

### 5.1 What "machine learning" means here

Nobody wrote a rule that says "if amount > X and SIM is new then fraud". Instead:

- We collected 30,000 past transactions where we already know the answer — 750 simulated customers,
  each transaction labelled `is_takeover = 0` or `1`.
- We fed the features and the labels to an algorithm.
- The algorithm found the patterns that separate the two groups.
- Now it can score a transaction it has never seen.

This is **supervised learning** ("supervised" because we had labelled answers to learn from) and
specifically **binary classification** (two possible classes) on **tabular data** (rows and columns,
like a spreadsheet — not images or text).

There are 61 features in total, but the model is only allowed to see 56 of them. The five that are
withheld — such as "has this recipient been confirmed as fraudulent?" — only become known *after*
an analyst has investigated a case. Training on them would let the model peek at the answer, a
mistake called **label leakage**, and the scores would look wonderful and mean nothing. Those five
signals are still used, but only by the transparent rules, where their timing is auditable.

### 5.2 Decision trees, then forests

A **decision tree** is a flowchart of yes/no questions learned from data: *is the balance drain above
0.8? → is the SIM new? → …* Each path ends in a verdict. A single tree is easy to read but fragile;
it memorises quirks of the training data. This is called **overfitting**: brilliant on data it has
seen, useless on data it has not.

A **random forest** fixes that by training many trees — 160 here — each on a random subset of the
data and features, then averaging their votes. Individually mediocre, collectively strong. The
settings used here are in `scripts/train_model.py`:

- `n_estimators=160` — 160 trees
- `max_depth=12` — no tree may ask more than 12 questions deep, another brake on overfitting
- `min_samples_leaf=4` — no conclusion may rest on fewer than 4 examples
- `class_weight="balanced_subsample"` — because fraud is rare, mistakes on fraud cases are weighted
  more heavily, otherwise the model would learn to say "not fraud" every time and be 99% accurate
  while being completely useless

### 5.3 Calibration: making 0.7 actually mean 70%

A raw random forest outputs a number between 0 and 1, but that number is not a trustworthy
probability — a raw output of 0.7 does not reliably mean "70 out of 100 cases like this are fraud".
Since the whole policy ladder is built on thresholds like 0.48 and 0.84, the numbers must mean
something real.

`CalibratedClassifierCV(method="sigmoid")` fixes this. It learns a correction curve, on held-back
data, that maps the model's raw outputs onto honest probabilities. The **Brier score** reported in
the evaluation measures how well-calibrated those probabilities are.

### 5.4 Why the data is split by time

The data is split **chronologically**: the first 65% for training, the next 17% for validation
(choosing thresholds), the last 18% for the final test. It is not shuffled randomly, and that is
deliberate. In fraud, shuffling lets the model learn from the future to predict the past, which
inflates the scores and never survives contact with production. Testing on the *later* data is the
honest version of the question: "trained on what we knew then, how would it do next month?"

### 5.5 Why "accuracy" is a trap here

Only about 0.81% of the events are takeovers — 44 out of 5,400 in the held-out test set. A model
that says "never fraud" scores 99.2% accuracy and catches nothing. Rare-event problems need
different measures:

| Term | Plain meaning | In this project |
|---|---|---|
| **True positive** | Real fraud, correctly flagged | The goal |
| **False positive** | Normal payment, wrongly flagged | An annoyed customer |
| **False negative** | Real fraud, missed | Stolen money |
| **Recall** | Of all real fraud, what share did we catch? | 90.91% at the confirmation threshold |
| **Precision** | Of everything we flagged, what share was really fraud? | 95.24% at that threshold |
| **False-positive rate** | Share of normal payments we disturbed | 0.0373% — 2 out of 5,356 |
| **ROC-AUC** | How well scores rank fraud above normal, 0.5 = coin flip, 1.0 = perfect | 0.9611 fused |
| **PR-AUC** | The same idea, but honest about rare classes | 0.9216 |
| **Brier score** | Are the probabilities themselves truthful? | Reported in `artifacts/evaluation.json` |

Recall and precision pull against each other. Catch more fraud and you disturb more innocent people;
disturb fewer people and you miss more fraud. The threshold ladder is exactly where that trade-off
is made, which is why those four numbers are governance constants rather than casual settings.

### 5.6 Confidence intervals, and why 40/44 is not "90.9%"

The held-out set has 44 real takeovers. Catching 40 gives 90.91% — but with only 44 cases, one or
two going the other way would move that figure several points. So the evaluation reports an
**interval** (roughly 82%–98%) instead of pretending the single number is precise. That habit —
quoting the range, not the point — is one of the more mature things in this codebase, and one of the
easier things for a beginner to carry into their own work.

### 5.7 Why there is a rulebook next to the model

The transparent anomaly scorer exists for reasons a pure-ML approach cannot satisfy:

- **Explainability.** A bank must tell a regulator and a customer *why*. "The forest said 0.81" is
  not an answer; "new SIM, new device, 92% of the balance, brand-new recipient" is.
- **Cold start.** A new customer has no history for the model to reason about. The rulebook still works.
- **Guarantees.** The security floors ensure certain dangerous combinations are *always* treated
  seriously, even if the model has never seen that pattern.
- **Measurability.** The evaluation runs an **ablation** — model alone, rules alone, floors alone —
  so you can see what each piece actually contributes. Here, the model alone catches 40/44 with
  2 false alarms; the rules alone catch 41/44 but with 112 false alarms. Together they do better
  than either.

---

## 6. The parts that are not machine learning

Most of this repository is ordinary software engineering, and honestly that is where most of the
work is in a real ML system. The model is a small box in a large machine.

| Piece | File | What it does |
|---|---|---|
| **Web API** | `src/oluso/api.py`, `app.py` | FastAPI service: receives events, checks API keys and roles, applies rate limits |
| **Orchestration** | `src/oluso/service.py` | Ties everything together for one scoring request |
| **Database** | `src/oluso/storage.py` | SQLite: accounts, events, decisions, feedback |
| **Audit chain** | `src/oluso/audit.py` | Each record is hashed together with the previous hash, so edits are detectable |
| **Outage mode** | `src/oluso/resilience.py` | If the network drops, the system degrades safely instead of guessing — it never reports a settlement that did not happen |
| **Cross-bank sharing** | `src/oluso/fraud_sketch.py` | Banks swap rotating, signed tokens about bad recipients without sharing customer records |
| **Dashboard** | `dashboard/app.py` | A Streamlit console for analysts |
| **Packaging** | `Dockerfile`, `docker-compose.yml` | Runs the whole thing in containers |
| **Tests** | `tests/` | 64 tests, 91% of lines covered |

Concepts worth knowing to read these:

- **REST API / JSON** — how one program asks another program for something over HTTP.
- **Hashing (SHA-256)** — a one-way fingerprint of data. Change one character, the fingerprint changes
  completely. Chaining each record's hash into the next makes a tamper-evident log.
- **HMAC** — hashing with a secret key, so only someone with the key can produce a valid token. Used
  to turn a recipient's account number into a shareable token that reveals nothing by itself.
- **Tokenisation** — replacing an identifier with a meaningless stand-in so that a leak of the
  database does not leak real phone numbers or account numbers.
- **Containers (Docker)** — packaging the app with everything it needs so it runs identically anywhere.

---

## 7. What the current results do and do not prove

The numbers in the README come from **synthetic data** — transactions generated by
`scripts/generate_synthetic.py`, not real customers. This is stated repeatedly in the documentation,
and it is the right thing to state.

What the evidence does show: the pipeline runs end to end, the features separate the simulated
attacks, the thresholds behave sensibly, decisions are reproducible, and it responds in about 33
milliseconds.

What it cannot show: how real Nigerian customers behave, how real attackers adapt once they know a
system is watching, how messy real telecom and gateway data is, or whether the model treats different
groups of people fairly. Those require consented real data, shadow deployment, fairness testing and
independent validation — all listed in `docs/MODEL_CARD.md` under "Required validation before
production".

The project is also honest about its failures, which is unusual and worth imitating: it discloses
that three deliberately slow, subtle attacks were missed, that one of four remote-control USSD
attacks slipped through, and that an adaptive attack search found a way to stay just under the
threshold at ₦48,000.

---

## 8. Vocabulary

**Machine learning terms**

| Term | Meaning |
|---|---|
| Feature | One input number describing the event, e.g. `balance_drain_ratio` |
| Label | The known answer used in training: takeover or not |
| Supervised learning | Learning from labelled examples |
| Binary classification | Predicting one of two classes |
| Training / validation / test | Data used to learn / to tune / to judge honestly, kept separate |
| Overfitting | Memorising the training data instead of learning the pattern |
| Class imbalance | One class is far rarer than the other, as fraud is |
| Random forest | Many decision trees voting together |
| Calibration | Making the output number a truthful probability |
| Threshold | The cut-off score at which you take an action |
| Ablation | Removing a component to measure what it contributed |
| Data leakage | Accidentally letting information from the future, or from the answer, into the inputs |
| Drift | The world changes and the model quietly goes stale |

**Project terms**

| Term | Meaning |
|---|---|
| Behavioural twin | The per-customer summary of normal habits |
| Security floor | A rule setting a minimum risk score for a dangerous combination |
| Fusion | Blending the model score and the anomaly score into one |
| Decision confidence | How well-supported the score is — separate from how risky it is |
| Regret budget | A cap on how often one customer may be disrupted in 30 days |
| Recourse | The concrete steps offered to a customer to clear an interrupted payment |
| Mule account | A recipient account used to receive and quickly cash out stolen money |
| Cold start | The state of a customer with too little history to reason about |
| Hard negative | A legitimate case designed to look suspicious, used to test for false alarms |

---

## 9. Poke at it yourself

Reading code is slower than watching it run. In order:

```bash
# 1. Install
uv sync --all-extras          # or: pip install -e '.[dev,dashboard]'
cp .env.example .env

# 2. Watch a fraud case get caught
python scripts/seed_demo.py

# 3. Start the API and click around the auto-generated docs
uvicorn app:app --reload --port 8000
#    then open http://localhost:8000/docs

# 4. Start the analyst dashboard
streamlit run dashboard/app.py

# 5. Rebuild the model from scratch and see the metrics
python scripts/generate_synthetic.py --rows 30000
python scripts/train_model.py
python scripts/evaluate_system.py
```

Then try these small experiments — each one teaches more than a chapter of reading:

1. Open `data/training_features.csv` in a spreadsheet. Sort by `is_takeover`. Look at what the
   fraud rows have in common.
2. In `src/oluso/policy.py`, change the `confirm` threshold from `0.48` to `0.40`, re-run
   `scripts/evaluate_system.py`, and watch recall rise while precision falls. That single experiment
   is the entire precision/recall trade-off, felt rather than read.
3. In `src/oluso/scoring.py`, set the weight of `new_sim` to `0.0` and re-run. See how much that one
   signal was carrying.
4. Use `POST /v1/events/score` from the `/docs` page with your own invented transaction. Try to
   construct one that scores just under 0.30. That is exactly what an attacker does.

---

## 10. What to learn, in what order

If you want to genuinely understand this project rather than just run it, this is a sensible order.
Do not try to learn it all at once — items 1 to 4 already let you follow the important parts.

1. **Python basics** (if needed) — functions, dictionaries, classes.
2. **What ML is**, and supervised learning in particular.
3. **Decision trees and random forests** — the actual algorithm used here.
4. **Precision, recall, ROC, and the confusion matrix** — the language of the results table.
5. **Imbalanced data and fraud detection** — why rare events are their own discipline.
6. **Calibration** — why probabilities need correcting.
7. **Feature engineering** — where most of the real gains in tabular ML come from.
8. **scikit-learn** — the library doing the work.
9. **FastAPI, SQLite, Docker, Streamlit** — the serving layer.
10. **Hashing and HMAC** — the audit and privacy machinery.
11. **Model cards and responsible AI** — why `docs/MODEL_CARD.md` exists.

---

## 11. Video resources

Every link below was checked against YouTube's oEmbed API on 18 September 2026, so the title and
channel shown here are the ones the link actually opens. Durations are deliberately omitted rather
than guessed.

**If you only watch five, watch these, in this order:**
StatQuest's gentle introduction → decision trees → random forests → the confusion matrix → ROC and AUC.
That is about an hour, and it covers the entire modelling core of this project.

### Start here: what ML actually is

- [A Gentle Introduction to Machine Learning](https://www.youtube.com/watch?v=Gv9_4yMHFhI) — *StatQuest with Josh Starmer*.
  Cuts through the jargon. Watch this before anything else.
- [Machine Learning for Everybody – Full Course](https://www.youtube.com/watch?v=i_LwzRVP7bg) — *freeCodeCamp.org*.
  A long, hands-on beginner course if you want depth rather than a summary.

### Decision trees and random forests — the actual algorithm used here

- [Decision and Classification Trees, Clearly Explained!!!](https://www.youtube.com/watch?v=_L39rN6gz7Y) — *StatQuest with Josh Starmer*.
  One tree, explained from scratch. This is the building block.
- [StatQuest: Random Forests Part 1 — Building, Using and Evaluating](https://www.youtube.com/watch?v=J4Wdy0Wc_xQ) — *StatQuest with Josh Starmer*.
  Exactly what `RandomForestClassifier` in `scripts/train_model.py` is doing with its 160 trees.

### Reading the results table

- [Machine Learning Fundamentals: The Confusion Matrix](https://www.youtube.com/watch?v=Kdsp6soqA7o) — *StatQuest with Josh Starmer*.
  True positives, false positives, false negatives — the four boxes behind every number in the README.
- [ROC and AUC, Clearly Explained!](https://www.youtube.com/watch?v=4jRBRDbJemM) — *StatQuest with Josh Starmer*.
  Explains the 0.9611 ROC-AUC figure and why thresholds are a choice, not a fact.

### Why rare events break your intuition

- [The medical test paradox, and redesigning Bayes' rule](https://www.youtube.com/watch?v=lG4VkPoG3ko) — *3Blue1Brown*.
  A rare disease and an accurate test produce mostly false alarms. Swap "disease" for "fraud" and
  you have this project's central difficulty.
- [Bayes theorem, the geometry of changing beliefs](https://www.youtube.com/watch?v=HZGCoVF3YvM) — *3Blue1Brown*.
  The underlying idea: how evidence should update a belief.

### Imbalanced data and fraud

- [Handling Imbalanced Dataset in Machine Learning: Easy Explanation](https://www.youtube.com/watch?v=GR-OW5asKlk) — *Emma Ding*.
  Short and clear on why 0.81% fraud prevalence needs special handling — related to the
  `class_weight="balanced_subsample"` setting in the training script.
- [How to handle imbalanced datasets in Python](https://www.youtube.com/watch?v=4SivdTLIwHc) — *Data Professor*.
  The practical, code-level version.

### Calibration

- [Probability Calibration For Machine Learning in Python](https://www.youtube.com/watch?v=wN4N7IBk16A) — *NeuralNine*.
  Covers `CalibratedClassifierCV`, the exact tool wrapped around the forest here, and why an
  uncalibrated 0.7 is not really 70%.

### Feature engineering

- [Feature Engineering for Tabular Data | Zhifeng Gao | Kaggle Days](https://www.youtube.com/watch?v=lUg0dRrlsoA) — *Kaggle*.
  Turning raw rows into meaningful signals, which is what `src/oluso/features.py` spends 649 lines doing.

### Anomaly detection

- [Anomaly Detection | ML-005 Lecture 15 | Stanford University | Andrew Ng](https://www.youtube.com/watch?v=UqqPm-Q4aMo) — re-uploaded on the channel *Machine Learning and AI*.
  The classic lecture on modelling "normal" and flagging departures from it — the idea behind the
  behavioural twin. Note this is a mirror of the Stanford course, not an official channel.

### scikit-learn, the library doing the work

- [Scikit-Learn Course — Machine Learning in Python Tutorial](https://www.youtube.com/watch?v=pqNCD_5r0IU) — *freeCodeCamp.org*.
- [Machine Learning with Python and Scikit-Learn – Full Course](https://www.youtube.com/watch?v=hDKCxebp88A) — *freeCodeCamp.org*.
  A newer, longer end-to-end walkthrough.

### The serving layer

- [FastAPI Course for Beginners](https://www.youtube.com/watch?v=tLKKmouUams) — *freeCodeCamp.org*.
  The framework behind `src/oluso/api.py` and the `/docs` page you clicked earlier.
- [Docker Tutorial for Beginners \[FULL COURSE in 3 Hours\]](https://www.youtube.com/watch?v=3c-iBn73dDE) — *TechWorld with Nana*.
  Explains the `Dockerfile` and `docker-compose.yml`.
- [SQL Tutorial — Full Database Course for Beginners](https://www.youtube.com/watch?v=HXV3zeQKqGY) — *freeCodeCamp.org*.
  Teaches MySQL rather than SQLite, but the SQL in `src/oluso/storage.py` is the same language.
- [Build 12 Data Science Apps with Python and Streamlit — Full Course](https://www.youtube.com/watch?v=JwSS70SZdyM) — *freeCodeCamp.org*.
  For understanding and extending `dashboard/app.py`.

### Hashing, HMAC and the audit chain

- [Hashing Algorithms and Security — Computerphile](https://www.youtube.com/watch?v=b4b8ktEV4Bg) — *Computerphile*.
  Start here: what a hash is and why it is useful.
- [SHA: Secure Hashing Algorithm — Computerphile](https://www.youtube.com/watch?v=DMtFhACPnTY) — *Computerphile*.
  The specific algorithm behind the tamper-evident audit log.
- [Securing Stream Ciphers (HMAC) — Computerphile](https://www.youtube.com/watch?v=wlSG3pEiQdc) — *Computerphile*.
  Hashing with a secret key — the mechanism behind the cross-bank recipient tokens.

### The problem domain

- [SIM swap scam explained | How scammers can take over your phone number](https://www.youtube.com/watch?v=8Muf8E_kkZQ) — *CTV News*.
  The attack this system is primarily built to catch, explained as a news segment.
- [How M-Pesa permanently changed Kenya's economy](https://www.youtube.com/watch?v=_BQeT4jEvk0) — *Phoebe Yu*.
  Why mobile money matters in Africa, and why USSD and agent channels exist at all.

### Responsibility and governance

- [Introduction to Responsible AI](https://www.youtube.com/watch?v=3-xhMXeYIcg) — *Google Cloud Tech*.
  Fairness, transparency and accountability — the thinking behind `docs/MODEL_CARD.md`, the
  reversible-action design and the "never treat a score as proof of guilt" rule.

---

## 12. Where to go next in this repository

Once the ideas above make sense, read in this order:

1. `README.md` — the full feature list and results
2. `docs/ARCHITECTURE.md` — how the components fit together
3. `docs/MODEL_CARD.md` — what the model is, and its limits
4. `docs/EVALUATION.md` — the full results with intervals and ablations
5. `src/oluso/features.py` — the features, which are the heart of the system
6. `src/oluso/scoring.py` — the rulebook, the floors, and the fusion
7. `src/oluso/policy.py` — how a score becomes an action
8. `docs/THREAT_MODEL.md` — who the attacker is and what they try
