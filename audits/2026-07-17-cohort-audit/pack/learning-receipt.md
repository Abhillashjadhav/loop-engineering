# Learning Receipt

## Important decisions

- identity was confirmed only from >=2 corroborating public attributes
- forks were excluded from authored-code scoring and reported separately
- negative (shallow/templated) classifications required slop risk >= 70, confidence >= 70, and a recorded counter-evidence review

## Alternatives rejected

- stating an exact AI-generated-code percentage — rejected; only conservative ranges with confidence are permitted without provenance logs
- using stars/forks as a quality input — rejected; distribution is reported as a reach signal only

## Key failures and repairs

- (none recorded)

## Surprising evidence

- (none recorded)

## What you should understand before using this conclusion

- scores describe public repository artifacts, not the person's private ability or intent
- AI-assistance likelihood and slop risk are different axes; high AI assistance does not mean low value
- six-run stability shows robustness of the pipeline's conclusions, not ground truth; evidence citations remain the accuracy anchor
