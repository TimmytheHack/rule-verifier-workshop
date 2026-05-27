# MVP Demo Result Trace

Every returned row passed the six executable rules. The 中外合作 preference is shown as not executed because the schema lacks a dedicated `cooperation_type` field.

Total returned rows: 93

## 1. 深圳大学 - 计算机类

- ID: `8947`
- Excel row: `8950`
- 专业组: `10590251 251组(地方专项)`
- 城市: `深圳`
- 学费: `6853`
- 专业组最低位次1: `38998`
- Ranking key: `3798`
- Safety margin vs user rank: `21.87%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 深圳 |
| `e_safety_margin` | pass | 专业组最低位次1 38998 >= 35200 |
| `e_tuition_cap` | pass | 学费 6853 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 2. 深圳技术大学 - 计算机科学与技术

- ID: `29574`
- Excel row: `29577`
- 专业组: `14655203 203组`
- 城市: `深圳`
- 学费: `6200`
- 专业组最低位次1: `42938`
- Ranking key: `7738`
- Safety margin vs user rank: `34.18%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 深圳 |
| `e_safety_margin` | pass | 专业组最低位次1 42938 >= 35200 |
| `e_tuition_cap` | pass | 学费 6200 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 3. 深圳技术大学 - 计算机科学与技术

- ID: `29575`
- Excel row: `29578`
- 专业组: `14655203 203组`
- 城市: `深圳`
- 学费: `6200`
- 专业组最低位次1: `42938`
- Ranking key: `7738`
- Safety margin vs user rank: `34.18%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 深圳 |
| `e_safety_margin` | pass | 专业组最低位次1 42938 >= 35200 |
| `e_tuition_cap` | pass | 学费 6200 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 4. 广东外语外贸大学 - 计算机类

- ID: `15841`
- Excel row: `15844`
- 专业组: `11846212 212组`
- 城市: `广州`
- 学费: `6853`
- 专业组最低位次1: `50802`
- Ranking key: `15602`
- Safety margin vs user rank: `58.76%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 50802 >= 35200 |
| `e_tuition_cap` | pass | 学费 6853 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 5. 广东工业大学(揭阳校区) - 计算机科学与技术

- ID: `30585`
- Excel row: `30588`
- 专业组: `80003252 252组`
- 城市: `广州`
- 学费: `6850`
- 专业组最低位次1: `58867`
- Ranking key: `23667`
- Safety margin vs user rank: `83.96%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 58867 >= 35200 |
| `e_tuition_cap` | pass | 学费 6850 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 6. 广东财经大学 - 计算机科学与技术

- ID: `9083`
- Excel row: `9086`
- 专业组: `10592219 219组(地方专项)`
- 城市: `广州`
- 学费: `6230`
- 专业组最低位次1: `68770`
- Ranking key: `33570`
- Safety margin vs user rank: `114.91%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 68770 >= 35200 |
| `e_tuition_cap` | pass | 学费 6230 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 7. 广东财经大学 - 计算机科学与技术

- ID: `9063`
- Excel row: `9066`
- 专业组: `10592212 212组`
- 城市: `广州`
- 学费: `6230`
- 专业组最低位次1: `71086`
- Ranking key: `35886`
- Safety margin vs user rank: `122.14%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 71086 >= 35200 |
| `e_tuition_cap` | pass | 学费 6230 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 8. 广东财经大学 - 计算机科学与技术

- ID: `9064`
- Excel row: `9067`
- 专业组: `10592212 212组`
- 城市: `广州`
- 学费: `6230`
- 专业组最低位次1: `71086`
- Ranking key: `35886`
- Safety margin vs user rank: `122.14%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 71086 >= 35200 |
| `e_tuition_cap` | pass | 学费 6230 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 9. 广州大学 - 计算机科学与技术

- ID: `12665`
- Excel row: `12668`
- 专业组: `11078203 203组`
- 城市: `广州`
- 学费: `6850`
- 专业组最低位次1: `75046`
- Ranking key: `39846`
- Safety margin vs user rank: `134.52%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 75046 >= 35200 |
| `e_tuition_cap` | pass | 学费 6850 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 10. 广东技术师范大学 - 计算机科学与技术

- ID: `8659`
- Excel row: `8662`
- 专业组: `10588205 205组(地方专项)`
- 城市: `广州`
- 学费: `5710`
- 专业组最低位次1: `82127`
- Ranking key: `46927`
- Safety margin vs user rank: `156.65%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 82127 >= 35200 |
| `e_tuition_cap` | pass | 学费 5710 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 11. 广东技术师范大学 - 计算机科学与技术

- ID: `8673`
- Excel row: `8676`
- 专业组: `10588208 208组`
- 城市: `广州`
- 学费: `5710`
- 专业组最低位次1: `88077`
- Ranking key: `52877`
- Safety margin vs user rank: `175.24%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 88077 >= 35200 |
| `e_tuition_cap` | pass | 学费 5710 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 12. 广东技术师范大学 - 计算机科学与技术

- ID: `8674`
- Excel row: `8677`
- 专业组: `10588208 208组`
- 城市: `广州`
- 学费: `5710`
- 专业组最低位次1: `88077`
- Ranking key: `52877`
- Safety margin vs user rank: `175.24%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 88077 >= 35200 |
| `e_tuition_cap` | pass | 学费 5710 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 13. 华南农业大学 - 计算机科学与技术

- ID: `7370`
- Excel row: `7373`
- 专业组: `10564252 252组(国际班)`
- 城市: `广州`
- 学费: `6853`
- 专业组最低位次1: `88276`
- Ranking key: `53076`
- Safety margin vs user rank: `175.86%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 88276 >= 35200 |
| `e_tuition_cap` | pass | 学费 6853 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 14. 广东第二师范学院 - 计算机科学与技术

- ID: `27939`
- Excel row: `27942`
- 专业组: `14278206 206组`
- 城市: `广州`
- 学费: `5190`
- 专业组最低位次1: `103608`
- Ranking key: `68408`
- Safety margin vs user rank: `223.78%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 103608 >= 35200 |
| `e_tuition_cap` | pass | 学费 5190 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 15. 广东金融学院 - 计算机科学与技术

- ID: `14641`
- Excel row: `14644`
- 专业组: `11540232 232组(地方专项)`
- 城市: `广州`
- 学费: `5710`
- 专业组最低位次1: `107535`
- Ranking key: `72335`
- Safety margin vs user rank: `236.05%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 107535 >= 35200 |
| `e_tuition_cap` | pass | 学费 5710 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 16. 广东金融学院 - 计算机科学与技术

- ID: `14619`
- Excel row: `14622`
- 专业组: `11540226 226组`
- 城市: `广州`
- 学费: `5710`
- 专业组最低位次1: `112025`
- Ranking key: `76825`
- Safety margin vs user rank: `250.08%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 112025 >= 35200 |
| `e_tuition_cap` | pass | 学费 5710 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 17. 广东金融学院 - 计算机科学与技术

- ID: `14625`
- Excel row: `14628`
- 专业组: `11540227 227组`
- 城市: `广州`
- 学费: `5710`
- 专业组最低位次1: `127132`
- Ranking key: `91932`
- Safety margin vs user rank: `297.29%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 127132 >= 35200 |
| `e_tuition_cap` | pass | 学费 5710 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 18. 仲恺农业工程学院 - 计算机科学与技术

- ID: `13900`
- Excel row: `13903`
- 专业组: `11347203 203组`
- 城市: `广州`
- 学费: `5710`
- 专业组最低位次1: `131971`
- Ranking key: `96771`
- Safety margin vs user rank: `312.41%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 131971 >= 35200 |
| `e_tuition_cap` | pass | 学费 5710 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 19. 广东技术师范大学 - 计算机科学与技术

- ID: `8718`
- Excel row: `8721`
- 专业组: `10588225 225组(国际班)`
- 城市: `广州`
- 学费: `5710`
- 专业组最低位次1: `135518`
- Ranking key: `100318`
- Safety margin vs user rank: `323.49%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 135518 >= 35200 |
| `e_tuition_cap` | pass | 学费 5710 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 20. 广州航海学院 - 计算机科学与技术

- ID: `12931`
- Excel row: `12934`
- 专业组: `11106201 201组`
- 城市: `广州`
- 学费: `5190`
- 专业组最低位次1: `138428`
- Ranking key: `103228`
- Safety margin vs user rank: `332.59%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 138428 >= 35200 |
| `e_tuition_cap` | pass | 学费 5190 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 21. 广东药科大学 - 计算机科学与技术

- ID: `7786`
- Excel row: `7789`
- 专业组: `10573205 205组`
- 城市: `广州`
- 学费: `8000`
- 专业组最低位次1: `143557`
- Ranking key: `108357`
- Safety margin vs user rank: `348.62%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 143557 >= 35200 |
| `e_tuition_cap` | pass | 学费 8000 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 22. 广东药科大学 - 计算机科学与技术

- ID: `7802`
- Excel row: `7805`
- 专业组: `10573205 205组`
- 城市: `广州`
- 学费: `6230`
- 专业组最低位次1: `143557`
- Ranking key: `108357`
- Safety margin vs user rank: `348.62%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 143557 >= 35200 |
| `e_tuition_cap` | pass | 学费 6230 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 23. 深圳职业技术大学 - 计算机网络技术

- ID: `13309`
- Excel row: `13312`
- 专业组: `11113531 531组`
- 城市: `深圳`
- 学费: `6000`
- 专业组最低位次1: `168764`
- Ranking key: `133564`
- Safety margin vs user rank: `427.39%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 深圳 |
| `e_safety_margin` | pass | 专业组最低位次1 168764 >= 35200 |
| `e_tuition_cap` | pass | 学费 6000 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 24. 深圳职业技术大学 - 计算机应用技术

- ID: `13314`
- Excel row: `13317`
- 专业组: `11113531 531组`
- 城市: `深圳`
- 学费: `6000`
- 专业组最低位次1: `168764`
- Ranking key: `133564`
- Safety margin vs user rank: `427.39%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 深圳 |
| `e_safety_margin` | pass | 专业组最低位次1 168764 >= 35200 |
| `e_tuition_cap` | pass | 学费 6000 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 25. 深圳信息职业技术学院 - 计算机应用技术

- ID: `20251`
- Excel row: `20254`
- 专业组: `12957516 516组`
- 城市: `深圳`
- 学费: `6000`
- 专业组最低位次1: `173030`
- Ranking key: `137830`
- Safety margin vs user rank: `440.72%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 深圳 |
| `e_safety_margin` | pass | 专业组最低位次1 173030 >= 35200 |
| `e_tuition_cap` | pass | 学费 6000 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 26. 深圳信息职业技术学院 - 计算机网络技术

- ID: `20252`
- Excel row: `20255`
- 专业组: `12957516 516组`
- 城市: `深圳`
- 学费: `6000`
- 专业组最低位次1: `173030`
- Ranking key: `137830`
- Safety margin vs user rank: `440.72%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 深圳 |
| `e_safety_margin` | pass | 专业组最低位次1 173030 >= 35200 |
| `e_tuition_cap` | pass | 学费 6000 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 27. 广东交通职业技术学院 - 计算机网络技术

- ID: `11964`
- Excel row: `11967`
- 专业组: `10861504 504组(高技能人才)`
- 城市: `广州`
- 学费: `6410`
- 专业组最低位次1: `173089`
- Ranking key: `137889`
- Safety margin vs user rank: `440.90%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 173089 >= 35200 |
| `e_tuition_cap` | pass | 学费 6410 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 28. 广州番禺职业技术学院 - 计算机应用技术

- ID: `16155`
- Excel row: `16158`
- 专业组: `12046508 508组`
- 城市: `广州`
- 学费: `6410`
- 专业组最低位次1: `203240`
- Ranking key: `168040`
- Safety margin vs user rank: `535.13%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 203240 >= 35200 |
| `e_tuition_cap` | pass | 学费 6410 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 29. 广州番禺职业技术学院 - 计算机网络技术

- ID: `16156`
- Excel row: `16159`
- 专业组: `12046508 508组`
- 城市: `广州`
- 学费: `6410`
- 专业组最低位次1: `203240`
- Ranking key: `168040`
- Safety margin vs user rank: `535.13%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 203240 >= 35200 |
| `e_tuition_cap` | pass | 学费 6410 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 30. 广东邮电职业技术学院 - 计算机应用技术

- ID: `20070`
- Excel row: `20073`
- 专业组: `12953507 507组(高技能人才)`
- 城市: `广州`
- 学费: `6410`
- 专业组最低位次1: `205904`
- Ranking key: `170704`
- Safety margin vs user rank: `543.45%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 205904 >= 35200 |
| `e_tuition_cap` | pass | 学费 6410 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 31. 深圳职业技术大学 - 计算机网络技术

- ID: `13389`
- Excel row: `13392`
- 专业组: `11113541 541组`
- 城市: `深圳`
- 学费: `6000`
- 专业组最低位次1: `218431`
- Ranking key: `183231`
- Safety margin vs user rank: `582.60%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 深圳 |
| `e_safety_margin` | pass | 专业组最低位次1 218431 >= 35200 |
| `e_tuition_cap` | pass | 学费 6000 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 32. 深圳职业技术大学 - 计算机应用技术

- ID: `13394`
- Excel row: `13397`
- 专业组: `11113541 541组`
- 城市: `深圳`
- 学费: `6000`
- 专业组最低位次1: `218431`
- Ranking key: `183231`
- Safety margin vs user rank: `582.60%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 深圳 |
| `e_safety_margin` | pass | 专业组最低位次1 218431 >= 35200 |
| `e_tuition_cap` | pass | 学费 6000 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 33. 深圳城市职业学院 - 计算机网络技术

- ID: `30133`
- Excel row: `30136`
- 专业组: `14845502 502组`
- 城市: `深圳`
- 学费: `6000`
- 专业组最低位次1: `220835`
- Ranking key: `185635`
- Safety margin vs user rank: `590.11%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 深圳 |
| `e_safety_margin` | pass | 专业组最低位次1 220835 >= 35200 |
| `e_tuition_cap` | pass | 学费 6000 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 34. 广东轻工职业技术大学 - 计算机类

- ID: `11783`
- Excel row: `11786`
- 专业组: `10833508 508组`
- 城市: `广州`
- 学费: `6410`
- 专业组最低位次1: `234988`
- Ranking key: `199788`
- Safety margin vs user rank: `634.34%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 234988 >= 35200 |
| `e_tuition_cap` | pass | 学费 6410 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 35. 广州铁路职业技术学院 - 计算机类

- ID: `25881`
- Excel row: `25884`
- 专业组: `13943505 505组`
- 城市: `广州`
- 学费: `6410`
- 专业组最低位次1: `243153`
- Ranking key: `207953`
- Safety margin vs user rank: `659.85%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 243153 >= 35200 |
| `e_tuition_cap` | pass | 学费 6410 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 36. 广东技术师范大学 - 计算机科学与技术

- ID: `8729`
- Excel row: `8732`
- 专业组: `10588230 230组(民族班)`
- 城市: `广州`
- 学费: `5710`
- 专业组最低位次1: `252780`
- Ranking key: `217580`
- Safety margin vs user rank: `689.94%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 252780 >= 35200 |
| `e_tuition_cap` | pass | 学费 5710 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 37. 深圳信息职业技术学院 - 计算机应用技术

- ID: `20245`
- Excel row: `20248`
- 专业组: `12957515 515组`
- 城市: `深圳`
- 学费: `6000`
- 专业组最低位次1: `260581`
- Ranking key: `225381`
- Safety margin vs user rank: `714.32%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 深圳 |
| `e_safety_margin` | pass | 专业组最低位次1 260581 >= 35200 |
| `e_tuition_cap` | pass | 学费 6000 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 38. 深圳信息职业技术学院 - 计算机网络技术

- ID: `20246`
- Excel row: `20249`
- 专业组: `12957515 515组`
- 城市: `深圳`
- 学费: `6000`
- 专业组最低位次1: `260581`
- Ranking key: `225381`
- Safety margin vs user rank: `714.32%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 深圳 |
| `e_safety_margin` | pass | 专业组最低位次1 260581 >= 35200 |
| `e_tuition_cap` | pass | 学费 6000 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 39. 广州民航职业技术学院 - 计算机应用技术

- ID: `16092`
- Excel row: `16095`
- 专业组: `12040504 504组`
- 城市: `广州`
- 学费: `6410`
- 专业组最低位次1: `262538`
- Ranking key: `227338`
- Safety margin vs user rank: `720.43%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 262538 >= 35200 |
| `e_tuition_cap` | pass | 学费 6410 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 40. 广州民航职业技术学院 - 计算机应用技术

- ID: `16105`
- Excel row: `16108`
- 专业组: `12040508 508组(高技能人才)`
- 城市: `广州`
- 学费: `6410`
- 专业组最低位次1: `264290`
- Ranking key: `229090`
- Safety margin vs user rank: `725.91%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 264290 >= 35200 |
| `e_tuition_cap` | pass | 学费 6410 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 41. 广东科学技术职业学院 - 计算机应用技术

- ID: `17375`
- Excel row: `17378`
- 专业组: `12572510 510组`
- 城市: `广州`
- 学费: `6410`
- 专业组最低位次1: `272933`
- Ranking key: `237733`
- Safety margin vs user rank: `752.92%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 272933 >= 35200 |
| `e_tuition_cap` | pass | 学费 6410 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 42. 广东工程职业技术学院 - 计算机网络技术

- ID: `25709`
- Excel row: `25712`
- 专业组: `13930510 510组(高技能人才)`
- 城市: `广州`
- 学费: `6410`
- 专业组最低位次1: `276006`
- Ranking key: `240806`
- Safety margin vs user rank: `762.52%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 276006 >= 35200 |
| `e_tuition_cap` | pass | 学费 6410 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 43. 广州城市职业学院 - 计算机应用技术

- ID: `25636`
- Excel row: `25639`
- 专业组: `13929506 506组`
- 城市: `广州`
- 学费: `6410`
- 专业组最低位次1: `278299`
- Ranking key: `243099`
- Safety margin vs user rank: `769.68%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 278299 >= 35200 |
| `e_tuition_cap` | pass | 学费 6410 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 44. 广东科学技术职业学院 - 计算机类

- ID: `17387`
- Excel row: `17390`
- 专业组: `12572512 512组`
- 城市: `广州`
- 学费: `6410`
- 专业组最低位次1: `279132`
- Ranking key: `243932`
- Safety margin vs user rank: `772.29%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 279132 >= 35200 |
| `e_tuition_cap` | pass | 学费 6410 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 45. 广州城市职业学院 - 计算机网络技术

- ID: `25663`
- Excel row: `25666`
- 专业组: `13929510 510组(高技能人才)`
- 城市: `广州`
- 学费: `6410`
- 专业组最低位次1: `281747`
- Ranking key: `246547`
- Safety margin vs user rank: `780.46%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 281747 >= 35200 |
| `e_tuition_cap` | pass | 学费 6410 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 46. 广东工贸职业技术学院 - 计算机网络技术

- ID: `20417`
- Excel row: `20420`
- 专业组: `12959501 501组`
- 城市: `广州`
- 学费: `6410`
- 专业组最低位次1: `285011`
- Ranking key: `249811`
- Safety margin vs user rank: `790.66%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 285011 >= 35200 |
| `e_tuition_cap` | pass | 学费 6410 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 47. 广东水利电力职业技术学院 - 计算机应用技术

- ID: `12044`
- Excel row: `12047`
- 专业组: `10862501 501组`
- 城市: `广州`
- 学费: `6410`
- 专业组最低位次1: `296547`
- Ranking key: `261347`
- Safety margin vs user rank: `826.71%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 296547 >= 35200 |
| `e_tuition_cap` | pass | 学费 6410 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 48. 广东工程职业技术学院 - 计算机应用技术

- ID: `25710`
- Excel row: `25713`
- 专业组: `13930513 513组(学分互认)`
- 城市: `广州`
- 学费: `18000`
- 专业组最低位次1: `302854`
- Ranking key: `267654`
- Safety margin vs user rank: `846.42%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 302854 >= 35200 |
| `e_tuition_cap` | pass | 学费 18000 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 49. 广东交通职业技术学院 - 计算机网络技术

- ID: `11922`
- Excel row: `11925`
- 专业组: `10861501 501组`
- 城市: `广州`
- 学费: `6410`
- 专业组最低位次1: `303326`
- Ranking key: `268126`
- Safety margin vs user rank: `847.89%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 303326 >= 35200 |
| `e_tuition_cap` | pass | 学费 6410 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 50. 广东司法警官职业学院 - 计算机网络技术

- ID: `20477`
- Excel row: `20480`
- 专业组: `12960501 501组`
- 城市: `广州`
- 学费: `6410`
- 专业组最低位次1: `303844`
- Ranking key: `268644`
- Safety margin vs user rank: `849.51%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 303844 >= 35200 |
| `e_tuition_cap` | pass | 学费 6410 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 51. 广东理工职业学院 - 计算机应用技术

- ID: `25276`
- Excel row: `25279`
- 专业组: `13919501 501组`
- 城市: `广州`
- 学费: `6410`
- 专业组最低位次1: `305637`
- Ranking key: `270437`
- Safety margin vs user rank: `855.12%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 305637 >= 35200 |
| `e_tuition_cap` | pass | 学费 6410 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 52. 广东理工职业学院 - 计算机网络技术

- ID: `25277`
- Excel row: `25280`
- 专业组: `13919501 501组`
- 城市: `广州`
- 学费: `6410`
- 专业组最低位次1: `305637`
- Ranking key: `270437`
- Safety margin vs user rank: `855.12%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 305637 >= 35200 |
| `e_tuition_cap` | pass | 学费 6410 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 53. 广东水利电力职业技术学院 - 计算机应用技术

- ID: `12055`
- Excel row: `12058`
- 专业组: `10862503 503组(中外合作)`
- 城市: `广州`
- 学费: `19600`
- 专业组最低位次1: `308769`
- Ranking key: `273569`
- Safety margin vs user rank: `864.90%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 308769 >= 35200 |
| `e_tuition_cap` | pass | 学费 19600 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 54. 广东邮电职业技术学院 - 计算机应用技术

- ID: `20044`
- Excel row: `20047`
- 专业组: `12953501 501组`
- 城市: `广州`
- 学费: `6410`
- 专业组最低位次1: `311720`
- Ranking key: `276520`
- Safety margin vs user rank: `874.13%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 311720 >= 35200 |
| `e_tuition_cap` | pass | 学费 6410 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 55. 广东建设职业技术学院 - 计算机应用技术

- ID: `18818`
- Excel row: `18821`
- 专业组: `12741501 501组`
- 城市: `广州`
- 学费: `6410`
- 专业组最低位次1: `313796`
- Ranking key: `278596`
- Safety margin vs user rank: `880.61%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 313796 >= 35200 |
| `e_tuition_cap` | pass | 学费 6410 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 56. 广州工程技术职业学院 - 计算机应用技术

- ID: `23358`
- Excel row: `23361`
- 专业组: `13709508 508组`
- 城市: `广州`
- 学费: `6410`
- 专业组最低位次1: `315855`
- Ranking key: `280655`
- Safety margin vs user rank: `887.05%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 315855 >= 35200 |
| `e_tuition_cap` | pass | 学费 6410 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 57. 广东农工商职业技术学院 - 计算机应用技术

- ID: `16822`
- Excel row: `16825`
- 专业组: `12322521 521组`
- 城市: `广州`
- 学费: `6410`
- 专业组最低位次1: `322946`
- Ranking key: `287746`
- Safety margin vs user rank: `909.21%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 322946 >= 35200 |
| `e_tuition_cap` | pass | 学费 6410 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 58. 广东农工商职业技术学院 - 计算机网络技术

- ID: `16823`
- Excel row: `16826`
- 专业组: `12322521 521组`
- 城市: `广州`
- 学费: `6410`
- 专业组最低位次1: `322946`
- Ranking key: `287746`
- Safety margin vs user rank: `909.21%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 322946 >= 35200 |
| `e_tuition_cap` | pass | 学费 6410 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 59. 广东生态工程职业学院 - 计算机应用技术

- ID: `28781`
- Excel row: `28784`
- 专业组: `14509508 508组`
- 城市: `广州`
- 学费: `6410`
- 专业组最低位次1: `325188`
- Ranking key: `289988`
- Safety margin vs user rank: `916.21%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 325188 >= 35200 |
| `e_tuition_cap` | pass | 学费 6410 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 60. 广东工程职业技术学院 - 计算机网络技术

- ID: `25675`
- Excel row: `25678`
- 专业组: `13930501 501组`
- 城市: `广州`
- 学费: `6410`
- 专业组最低位次1: `333256`
- Ranking key: `298056`
- Safety margin vs user rank: `941.42%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 333256 >= 35200 |
| `e_tuition_cap` | pass | 学费 6410 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 61. 广东工程职业技术学院 - 计算机应用技术

- ID: `25676`
- Excel row: `25679`
- 专业组: `13930501 501组`
- 城市: `广州`
- 学费: `6410`
- 专业组最低位次1: `333256`
- Ranking key: `298056`
- Safety margin vs user rank: `941.42%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 333256 >= 35200 |
| `e_tuition_cap` | pass | 学费 6410 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 62. 广东行政职业学院 - 计算机网络技术

- ID: `17663`
- Excel row: `17666`
- 专业组: `12577502 502组`
- 城市: `广州`
- 学费: `6410`
- 专业组最低位次1: `341478`
- Ranking key: `306278`
- Safety margin vs user rank: `967.12%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 341478 >= 35200 |
| `e_tuition_cap` | pass | 学费 6410 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 63. 广东科贸职业学院 - 计算机网络技术

- ID: `26477`
- Excel row: `26480`
- 专业组: `14063501 501组`
- 城市: `广州`
- 学费: `6410`
- 专业组最低位次1: `345794`
- Ranking key: `310594`
- Safety margin vs user rank: `980.61%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 345794 >= 35200 |
| `e_tuition_cap` | pass | 学费 6410 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 64. 广东省外语艺术职业学院 - 计算机应用技术

- ID: `20597`
- Excel row: `20600`
- 专业组: `12962536 536组`
- 城市: `广州`
- 学费: `6410`
- 专业组最低位次1: `349233`
- Ranking key: `314033`
- Safety margin vs user rank: `991.35%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 349233 >= 35200 |
| `e_tuition_cap` | pass | 学费 6410 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 65. 广州华立科技职业学院 - 计算机应用技术

- ID: `25576`
- Excel row: `25579`
- 专业组: `13928506 506组`
- 城市: `广州`
- 学费: `19800`
- 专业组最低位次1: `353556`
- Ranking key: `318356`
- Safety margin vs user rank: `1004.86%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 353556 >= 35200 |
| `e_tuition_cap` | pass | 学费 19800 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 66. 广州华立科技职业学院 - 计算机网络技术

- ID: `25577`
- Excel row: `25580`
- 专业组: `13928506 506组`
- 城市: `广州`
- 学费: `19800`
- 专业组最低位次1: `353556`
- Ranking key: `318356`
- Safety margin vs user rank: `1004.86%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 353556 >= 35200 |
| `e_tuition_cap` | pass | 学费 19800 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 67. 广东女子职业技术学院 - 计算机应用技术

- ID: `18924`
- Excel row: `18927`
- 专业组: `12742520 520组`
- 城市: `广州`
- 学费: `6410`
- 专业组最低位次1: `355082`
- Ranking key: `319882`
- Safety margin vs user rank: `1009.63%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 355082 >= 35200 |
| `e_tuition_cap` | pass | 学费 6410 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 68. 广州康大职业技术学院 - 计算机应用技术

- ID: `17570`
- Excel row: `17573`
- 专业组: `12575504 504组`
- 城市: `广州`
- 学费: `19900`
- 专业组最低位次1: `360149`
- Ranking key: `324949`
- Safety margin vs user rank: `1025.47%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 360149 >= 35200 |
| `e_tuition_cap` | pass | 学费 19900 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 69. 广州康大职业技术学院 - 计算机网络技术

- ID: `17572`
- Excel row: `17575`
- 专业组: `12575504 504组`
- 城市: `广州`
- 学费: `19900`
- 专业组最低位次1: `360149`
- Ranking key: `324949`
- Safety margin vs user rank: `1025.47%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 360149 >= 35200 |
| `e_tuition_cap` | pass | 学费 19900 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 70. 广州城建职业学院 - 计算机应用技术

- ID: `27091`
- Excel row: `27094`
- 专业组: `14136503 503组`
- 城市: `广州`
- 学费: `20000`
- 专业组最低位次1: `360374`
- Ranking key: `325174`
- Safety margin vs user rank: `1026.17%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 360374 >= 35200 |
| `e_tuition_cap` | pass | 学费 20000 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 71. 广州现代信息工程职业技术学院 - 计算机应用技术

- ID: `25225`
- Excel row: `25228`
- 专业组: `13912502 502组`
- 城市: `广州`
- 学费: `19800`
- 专业组最低位次1: `368071`
- Ranking key: `332871`
- Safety margin vs user rank: `1050.22%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 368071 >= 35200 |
| `e_tuition_cap` | pass | 学费 19800 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 72. 广州现代信息工程职业技术学院 - 计算机网络技术

- ID: `25226`
- Excel row: `25229`
- 专业组: `13912502 502组`
- 城市: `广州`
- 学费: `19800`
- 专业组最低位次1: `368071`
- Ranking key: `332871`
- Safety margin vs user rank: `1050.22%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 368071 >= 35200 |
| `e_tuition_cap` | pass | 学费 19800 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 73. 广州现代信息工程职业技术学院 - 计算机应用技术

- ID: `25238`
- Excel row: `25241`
- 专业组: `13912502 502组`
- 城市: `广州`
- 学费: `17800`
- 专业组最低位次1: `368071`
- Ranking key: `332871`
- Safety margin vs user rank: `1050.22%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 368071 >= 35200 |
| `e_tuition_cap` | pass | 学费 17800 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 74. 广州现代信息工程职业技术学院 - 计算机网络技术

- ID: `25239`
- Excel row: `25242`
- 专业组: `13912502 502组`
- 城市: `广州`
- 学费: `17800`
- 专业组最低位次1: `368071`
- Ranking key: `332871`
- Safety margin vs user rank: `1050.22%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 368071 >= 35200 |
| `e_tuition_cap` | pass | 学费 17800 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 75. 广东岭南职业技术学院 - 计算机网络技术

- ID: `19078`
- Excel row: `19081`
- 专业组: `12749502 502组`
- 城市: `广州`
- 学费: `19800`
- 专业组最低位次1: `369902`
- Ranking key: `334702`
- Safety margin vs user rank: `1055.94%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 369902 >= 35200 |
| `e_tuition_cap` | pass | 学费 19800 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 76. 广东艺术职业学院 - 计算机应用技术

- ID: `28445`
- Excel row: `28448`
- 专业组: `14407502 502组`
- 城市: `广州`
- 学费: `6410`
- 专业组最低位次1: `375200`
- Ranking key: `340000`
- Safety margin vs user rank: `1072.50%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 375200 >= 35200 |
| `e_tuition_cap` | pass | 学费 6410 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 77. 广州珠江职业技术学院 - 计算机应用技术

- ID: `26792`
- Excel row: `26795`
- 专业组: `14123508 508组`
- 城市: `广州`
- 学费: `18000`
- 专业组最低位次1: `383264`
- Ranking key: `348064`
- Safety margin vs user rank: `1097.70%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 383264 >= 35200 |
| `e_tuition_cap` | pass | 学费 18000 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 78. 广州华商职业学院 - 计算机网络技术

- ID: `27764`
- Excel row: `27767`
- 专业组: `14266505 505组`
- 城市: `广州`
- 学费: `19500`
- 专业组最低位次1: `385795`
- Ranking key: `350595`
- Safety margin vs user rank: `1105.61%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 385795 >= 35200 |
| `e_tuition_cap` | pass | 学费 19500 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 79. 广东新安职业技术学院 - 计算机应用技术

- ID: `16869`
- Excel row: `16872`
- 专业组: `12325501 501组`
- 城市: `深圳`
- 学费: `19800`
- 专业组最低位次1: `386170`
- Ranking key: `350970`
- Safety margin vs user rank: `1106.78%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 深圳 |
| `e_safety_margin` | pass | 专业组最低位次1 386170 >= 35200 |
| `e_tuition_cap` | pass | 学费 19800 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 80. 广东新安职业技术学院 - 计算机网络技术

- ID: `16870`
- Excel row: `16873`
- 专业组: `12325501 501组`
- 城市: `深圳`
- 学费: `19800`
- 专业组最低位次1: `386170`
- Ranking key: `350970`
- Safety margin vs user rank: `1106.78%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 深圳 |
| `e_safety_margin` | pass | 专业组最低位次1 386170 >= 35200 |
| `e_tuition_cap` | pass | 学费 19800 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 81. 广州南洋理工职业学院 - 计算机应用技术

- ID: `23871`
- Excel row: `23874`
- 专业组: `13716502 502组`
- 城市: `广州`
- 学费: `19000`
- 专业组最低位次1: `390272`
- Ranking key: `355072`
- Safety margin vs user rank: `1119.60%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 390272 >= 35200 |
| `e_tuition_cap` | pass | 学费 19000 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 82. 广州南洋理工职业学院 - 计算机网络技术

- ID: `23872`
- Excel row: `23875`
- 专业组: `13716502 502组`
- 城市: `广州`
- 学费: `19000`
- 专业组最低位次1: `390272`
- Ranking key: `355072`
- Safety margin vs user rank: `1119.60%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 390272 >= 35200 |
| `e_tuition_cap` | pass | 学费 19000 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 83. 广州松田职业学院 - 计算机应用技术

- ID: `26875`
- Excel row: `26878`
- 专业组: `14125502 502组`
- 城市: `广州`
- 学费: `18800`
- 专业组最低位次1: `394689`
- Ranking key: `359489`
- Safety margin vs user rank: `1133.40%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 394689 >= 35200 |
| `e_tuition_cap` | pass | 学费 18800 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 84. 广州松田职业学院 - 计算机网络技术

- ID: `26876`
- Excel row: `26879`
- 专业组: `14125502 502组`
- 城市: `广州`
- 学费: `18800`
- 专业组最低位次1: `394689`
- Ranking key: `359489`
- Safety margin vs user rank: `1133.40%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 394689 >= 35200 |
| `e_tuition_cap` | pass | 学费 18800 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 85. 广州涉外经济职业技术学院 - 计算机网络技术

- ID: `23775`
- Excel row: `23778`
- 专业组: `13715504 504组`
- 城市: `广州`
- 学费: `19800`
- 专业组最低位次1: `399845`
- Ranking key: `364645`
- Safety margin vs user rank: `1149.52%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 399845 >= 35200 |
| `e_tuition_cap` | pass | 学费 19800 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 86. 广州华南商贸职业学院 - 计算机应用技术

- ID: `25397`
- Excel row: `25400`
- 专业组: `13927501 501组`
- 城市: `广州`
- 学费: `19000`
- 专业组最低位次1: `404260`
- Ranking key: `369060`
- Safety margin vs user rank: `1163.31%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 404260 >= 35200 |
| `e_tuition_cap` | pass | 学费 19000 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 87. 广州华南商贸职业学院 - 计算机网络技术

- ID: `25398`
- Excel row: `25401`
- 专业组: `13927501 501组`
- 城市: `广州`
- 学费: `19000`
- 专业组最低位次1: `404260`
- Ranking key: `369060`
- Safety margin vs user rank: `1163.31%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 404260 >= 35200 |
| `e_tuition_cap` | pass | 学费 19000 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 88. 广州华商职业学院 - 计算机网络技术

- ID: `27736`
- Excel row: `27739`
- 专业组: `14266504 504组`
- 城市: `广州`
- 学费: `19500`
- 专业组最低位次1: `417595`
- Ranking key: `382395`
- Safety margin vs user rank: `1204.98%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 417595 >= 35200 |
| `e_tuition_cap` | pass | 学费 19500 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 89. 广州东华职业学院 - 计算机应用技术

- ID: `28208`
- Excel row: `28211`
- 专业组: `14362512 512组`
- 城市: `广州`
- 学费: `19800`
- 专业组最低位次1: `418090`
- Ranking key: `382890`
- Safety margin vs user rank: `1206.53%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 418090 >= 35200 |
| `e_tuition_cap` | pass | 学费 19800 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 90. 广州涉外经济职业技术学院 - 计算机应用技术

- ID: `23762`
- Excel row: `23765`
- 专业组: `13715502 502组`
- 城市: `广州`
- 学费: `19800`
- 专业组最低位次1: `419462`
- Ranking key: `384262`
- Safety margin vs user rank: `1210.82%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 419462 >= 35200 |
| `e_tuition_cap` | pass | 学费 19800 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 91. 私立华联学院 - 计算机应用技术

- ID: `13594`
- Excel row: `13597`
- 专业组: `11121502 502组`
- 城市: `广州`
- 学费: `18000`
- 专业组最低位次1: `427760`
- Ranking key: `392560`
- Safety margin vs user rank: `1236.75%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 427760 >= 35200 |
| `e_tuition_cap` | pass | 学费 18000 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 92. 私立华联学院 - 计算机网络技术

- ID: `13624`
- Excel row: `13627`
- 专业组: `11121502 502组`
- 城市: `广州`
- 学费: `19800`
- 专业组最低位次1: `427760`
- Ranking key: `392560`
- Safety margin vs user rank: `1236.75%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 427760 >= 35200 |
| `e_tuition_cap` | pass | 学费 19800 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |

## 93. 广州华立科技职业学院 - 计算机网络技术

- ID: `25525`
- Excel row: `25528`
- 专业组: `13928503 503组`
- 城市: `广州`
- 学费: `16800`
- 专业组最低位次1: `428749`
- Ranking key: `393549`
- Safety margin vs user rank: `1239.84%`

| Rule | Status | Reason |
|---|---|---|
| `e_source_province` | pass | 生源地 == 广东 |
| `e_subject_type` | pass | 科类 == 物理 |
| `e_major_keyword` | pass | 专业名称 contains 计算机 |
| `e_city` | pass | 城市 matches 广州 |
| `e_safety_margin` | pass | 专业组最低位次1 428749 >= 35200 |
| `e_tuition_cap` | pass | 学费 16800 <= 20000 |
| `l_cooperation_type` | not_executed | Missing dedicated cooperation_type field; no text inference applied. |
