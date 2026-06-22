# Evaluation Report

*To be filled after running the evaluation pipeline.*

## Model Configuration
- **Model**: OpenAI GPT-4o
- **API calls per claim**: 2 (claim_parser + image_analyst)
- **Rate limiting**: 2s sleep between claims
- **Retry policy**: max 3 retries, backoff (10s/30s)

## Metrics

### Sample Set (20 claims)
| Metric | Value |
|---|---|
| claim_status accuracy | 85.0% |
| issue_type accuracy | 50.0% |
| object_part accuracy | 80.0% |
| severity accuracy | 50.0% |
| evidence_standard_met accuracy | 85.0% |
| valid_image accuracy | 90.0% |
| risk_flags Jaccard | 0.641 |
| Overall field accuracy | 73.3% |

## Cost & Performance Analysis

### API Calls
| Set | Claims | Calls per claim | Total calls |
|---|---|---|---|
| Sample | 20 | 2 | ~40 |
| Test | 44 | 2 | ~88 |

### Token Usage (approximate)
| Call Type | Avg Input Tokens | Avg Output Tokens |
|---|---|---|
| Claim Parser | ~300 | ~100 |
| Image Analyst | ~500 + images | ~200 |

### Images Processed
| Set | Total images |
|---|---|
| Sample | 27 |
| Test | TBD |

### Cost Estimate
- OpenAI GPT-4o pricing
- Estimated cost for test set: Negligible (within small usage)

### Latency
- Per claim: ~4-6s (2s sleep + processing)
- Sample set (20 claims): ~2 minutes
- Test set (44 claims): ~4 minutes

### TPM/RPM Strategy
- **Rate limit**: Handles OpenAI rate limits
- **Strategy**: 2-second sleep between every claim API call
- **Batching**: all images for one claim sent in a single vision call
- **Retry**: backoff prevents thundering herd on transient failures
- **Caching**: not implemented (each claim is unique)

