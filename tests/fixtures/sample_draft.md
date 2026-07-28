# Adaptive Machine Learning for Financial Fraud Detection

## Introduction

Machine learning techniques have improved the ability to identify complex fraud patterns in financial transactions. Fraudulent activity nevertheless remains a rare event relative to legitimate payment volume. This paper investigates whether adaptive retraining narrows that gap.

Prior studies show that blockchain increases transparency in accounting processes [2]. Transformer-based models outperform traditional machine learning methods in text classification. We do not address natural language inputs in this work.

## Related Work

Several studies report that class imbalance degrades the precision of anomaly detectors on transaction data. Graph-based representations reveal collusive behaviour that account-level features cannot capture. According to Smith et al. (2024), learned models adapt to previously unseen fraud schemes.

Deployed detectors lose a substantial share of their recall within months of release, e.g. as retraining cycles fall behind changing attacker behaviour. Table 1 summarises the reviewed systems.

## Methodology

This study uses a quantitative experimental design. The next section describes the proposed retraining framework. We evaluate all models on the same held-out period.

## Results

Adaptive retraining raised recall by 8.4 percent relative to the static baseline. Accuracy is a misleading metric when the positive class is rare. Table 2 presents the experimental results.
