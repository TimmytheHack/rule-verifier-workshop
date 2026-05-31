# Excel Schema Profile

This report is generated automatically from the workbook. It is not an executable schema by itself.

- Workbook: `广东省2025年志愿填报大数据（24-25）0523.xlsx`
- Sheet: `Sheet1`
- Header row: `3`
- Data rows: `30855`
- Columns profiled: `57`

## Methodology

The system should not inspect every row manually. Instead, it should:

1. Detect the real header row.
2. Profile every column automatically.
3. Generate a field catalog with types, coverage, examples, and semantic hints.
4. Let a human promote only trusted fields into `schema_registry.json`.
5. Keep unsupported preferences non-executable until a verified field exists.

## Field Catalog

| # | Source column | Suggested field ID | Type | Coverage | Unique | Registry action | Samples |
|---:|---|---|---|---:|---:|---|---|
| 1 | `ID` | `row_id` | `number` | 100.0% | 30855 | `candidate_for_schema_registry` | 1<br>2<br>3 |
| 2 | `年份` | `year` | `number` | 100.0% | 1 | `candidate_for_schema_registry` | 2024 |
| 3 | `生源地` | `source_province` | `enum_or_category` | 100.0% | 1 | `candidate_for_schema_registry` | 广东 |
| 4 | `批次` | `batch` | `enum_or_category` | 100.0% | 4 | `candidate_for_schema_registry` | 本科提前批<br>本科批<br>专科高职批 |
| 5 | `科类` | `subject_type` | `enum_or_category` | 100.0% | 2 | `candidate_for_schema_registry` | 历史<br>物理 |
| 6 | `院校代码` | `school_code` | `number_from_string` | 100.0% | 1623 | `candidate_for_schema_registry` | 10001<br>10002<br>10003 |
| 7 | `院校名称` | `school_name` | `enum_or_category` | 100.0% | 1624 | `candidate_for_schema_registry` | 北京大学<br>中国人民大学<br>清华大学 |
| 8 | `院校专业组代码` | `school_major_group_code` | `number_from_string` | 100.0% | 7731 | `candidate_for_schema_registry` | 10001101<br>10001102<br>10001201 |
| 9 | `专业组名称` | `major_group_name` | `number_from_string` | 100.0% | 617 | `candidate_for_schema_registry` | 101组<br>102组<br>201组 |
| 10 | `专业组代码` | `major_group_code` | `number_from_string` | 100.0% | 211 | `candidate_for_schema_registry` | 101<br>102<br>201 |
| 11 | `专业代码` | `major_code` | `number_from_string` | 100.0% | 484 | `candidate_for_schema_registry` | 001<br>002<br>003 |
| 12 | `专业全称` | `major_full_name` | `enum_or_category` | 100.0% | 16669 | `candidate_for_schema_registry` | 法语(校本部)(语种：英语)<br>德语(校本部)(语种：英语)<br>西班牙语(校本部)(语种：英语) |
| 13 | `专业名称` | `major_name` | `enum_or_category` | 100.0% | 1219 | `candidate_for_schema_registry` | 法语<br>德语<br>西班牙语 |
| 14 | `专业备注` | `major_notes` | `long_text` | 100.0% | 6130 | `candidate_for_schema_registry` | (校本部)(语种：英语)<br>(元培，含：语言文学类、考古学、历史学类、哲学类、社会学类、法学、新闻传播学类、经济学类、工商管理类、公共管理类，校本部)<br>(含：汉语言文学、汉语言、古典文献学、应用语言学，校本部) |
| 15 | `专业层次` | `degree_level` | `enum_or_category` | 100.0% | 3 | `candidate_for_schema_registry` | 本科<br>专科<br>职教本科 |
| 16 | `选科要求` | `subject_requirement` | `enum_or_category` | 100.0% | 12 | `candidate_for_schema_registry` | 不限<br>化学<br>政治 |
| 17 | `计划人数` | `plan_count` | `number` | 100.0% | 275 | `candidate_for_schema_registry` | 1<br>2<br>5 |
| 18 | `学制` | `program_duration` | `number` | 100.0% | 8 | `candidate_for_schema_registry` | 4<br>5<br>8 |
| 19 | `学费` | `tuition_yuan_per_year` | `number_from_string` | 100.0% | 534 | `candidate_for_schema_registry` | 5000<br>5300<br>6000 |
| 20 | `组内专业` | `majors_in_group` | `number_from_string` | 100.0% | 7730 | `candidate_for_schema_registry` | 001 法语 (校本部)(语种：英语) 【4年，5000元，1人】 【录取人数: ，最低分: ，最低位次: 】
002 德语 (校本部)(语种：英语) 【4年，5000元，1人】 【录取人数: ，最低分: ，最低位次: 】
003 西班牙语<br>009 法语 (校本部)(语种：英语) 【4年，5000元，1人】 【录取人数: ，最低分: ，最低位次: 】
010 德语 (校本部)(语种：英语) 【4年，5000元，1人】 【录取人数: ，最低分: ，最低位次: 】
011 日语 (<br>090 文科试验班类 (元培，含：语言文学类、考古学、历史学类、哲学类、社会学类、法学、新闻传播学类、经济学类、工商管理类、公共管理类，校本部) 【4年，5300元，1人】 【录取人数: ，最低分: ，最低位次: 】
091 中国语言文学类 |
| 21 | `门类` | `discipline_category` | `enum_or_category` | 100.0% | 36 | `candidate_for_schema_registry` | 文学<br>试验班<br>历史学 |
| 22 | `专业类` | `major_category` | `enum_or_category` | 100.0% | 182 | `candidate_for_schema_registry` | 外国语言文学类<br>文科试验班类<br>中国语言文学类 |
| 23 | `专业组计划人数` | `major_group_plan_count` | `number` | 100.0% | 551 | `candidate_for_schema_registry` | 8<br>4<br>24 |
| 24 | `25年预估位次` | `estimated_rank_2025` | `mostly_empty` | 0.0% | 0 | `review_before_use` |  |
| 25 | `是否新增` | `is_new` | `mostly_empty` | 0.0% | 0 | `review_before_use` |  |
| 26 | `专业组录取人数1` | `major_group_admit_count_2024` | `number` | 98.8% | 582 | `candidate_for_schema_registry` | 8<br>4<br>24 |
| 27 | `专业组最低分1` | `major_group_min_score_2024` | `number` | 98.8% | 430 | `candidate_for_schema_registry` | 659<br>674<br>662 |
| 28 | `专业组最低位次1` | `major_group_min_rank_2024` | `number` | 98.8% | 7328 | `candidate_for_schema_registry` | 49<br>466<br>32 |
| 29 | `录取人数1` | `admit_count_2024` | `number` | 33.8% | 226 | `candidate_for_schema_registry` | 2<br>3<br>4 |
| 30 | `最低分1` | `min_score_2024` | `number` | 33.8% | 349 | `candidate_for_schema_registry` | 594<br>596<br>595 |
| 31 | `最低位次1` | `min_rank_2024` | `number` | 33.8% | 637 | `candidate_for_schema_registry` | 3872<br>24887<br>25601 |
| 32 | `最高分1` | `max_score_2024` | `number` | 29.8% | 336 | `candidate_for_schema_registry` | 594<br>595<br>601 |
| 33 | `最高位次1` | `max_rank_2024` | `number` | 29.8% | 609 | `candidate_for_schema_registry` | 3872<br>3709<br>2945 |
| 34 | `所在省` | `school_province` | `enum_or_category` | 100.0% | 33 | `candidate_for_schema_registry` | 北京<br>天津<br>河北 |
| 35 | `城市` | `city` | `enum_or_category` | 100.0% | 313 | `candidate_for_schema_registry` | 海淀区<br>朝阳区<br>大兴区 |
| 36 | `院校标签` | `school_tags` | `enum_or_category` | 45.5% | 51 | `candidate_for_schema_registry` | 985/211/双一流/国重点/保研资格<br>211/双一流/国重点/保研资格<br>省重点/保研资格 |
| 37 | `院校水平` | `school_level` | `string` | 43.0% | 253 | `candidate_for_schema_registry` | 原卫生部直属/基础学科拔尖/卓越医生/卓越法律/五院四系/C9联盟/部委直属<br>基础学科拔尖/卓越法律/卓越农林/五院四系/部委直属<br>原轻工业部直属/基础学科拔尖/卓越工程师/卓越医生/卓越法律/建筑老八校/电气四虎/C9联盟/部委直属 |
| 38 | `更名合并转设` | `school_change_history` | `enum_or_category` | 38.1% | 561 | `candidate_for_schema_registry` | 2000年，北京医科大学并入<br>1999年，中央工艺美术学院并入<br>原北方交通大学 |
| 39 | `转专业情况` | `major_transfer_policy` | `long_text` | 43.8% | 563 | `candidate_for_schema_registry` | 在第二、四学期，凡符合学校和各学院规定的转专业条件的学生，均可提出转专业申请，经考核，成绩合格者可以转入新专业学习。<br>大一结束后。4.10左右，各个学院会公布报名条件和考核办法
4.13～4.17各个学院组织报名，交申请表
4.23转专业初试（只有数学）
4.29前，教务处将数学考试成绩公布给各学院
4.29～5.6<br>大一学期末，成绩专业前15%可以全校选择，前20%可以院内选择。
一．转专业的条件
（一）一年级第一学期所修课程的加权平均分超过70分（含）；
（二）入学以来未受过任何纪律处分；
（三）转专业只限一次 |
| 40 | `城市水平标签` | `city_level_tag` | `enum_or_category` | 99.8% | 11 | `candidate_for_schema_registry` | 一线城市<br>新一线城市<br>三线城市 |
| 41 | `本科/专科` | `undergraduate_or_junior` | `enum_or_category` | 100.0% | 3 | `candidate_for_schema_registry` | 本科<br>专科<br>职业本科 |
| 42 | `隶属单位` | `supervising_department` | `enum_or_category` | 99.6% | 37 | `candidate_for_schema_registry` | 教育部<br>北京市政府<br>工信部 |
| 43 | `类型` | `school_type` | `enum_or_category` | 99.8% | 36 | `candidate_for_schema_registry` | 综合<br>理工<br>综合 农林 |
| 44 | `公私性质` | `school_ownership` | `enum_or_category` | 100.0% | 5 | `candidate_for_schema_registry` | 公办<br>民办<br>中外合作办学 |
| 45 | `保研率` | `postgraduate_recommendation_rate` | `enum_or_category` | 100.0% | 182 | `candidate_for_schema_registry` | 58.6%<br>35.9%<br>59.0% |
| 46 | `院校排名` | `school_ranking` | `number` | 100.0% | 470 | `candidate_for_schema_registry` | 2<br>18<br>1 |
| 47 | `全校硕士专业数` | `school_master_program_count` | `number` | 46.2% | 90 | `candidate_for_schema_registry` | 78<br>71<br>74 |
| 48 | `全校硕士专业` | `school_master_programs` | `long_text` | 46.2% | 607 | `candidate_for_schema_registry` | 保险(专)；博物馆(专)；材料科学与工程；材料与化工(专)；测绘科学与技术；大气科学；地理学；地球物理学；地质学；电子科学与技术；电子信息(专)；法律(专)；法学；翻译(专)；风景园林(专)；工程管理(专)；工商管理(专)；工商管理学；公共<br>安全科学与工程；保险(专)；博物馆(专)；党务管理(专)；地理学；电子信息(专)；法律(专)；法学；翻译(专)；工商管理(专)；工商管理学；公共管理(专)；公共管理学；公共卫生与预防医学；管理科学与工程；国际商务(专)；国际事务(专)；国际<br>安全科学与工程；材料科学与工程；材料与化工(专)；城乡规划(专)；城乡规划学；电气工程(专)；电子科学与技术；电子信息(专)；动力工程及工程热物理；法律(专)；法学；风景园林(专)；工程管理(专)；工商管理(专)；工商管理学；公共管理(专) |
| 49 | `全校博士专业数` | `school_phd_program_count` | `number` | 35.1% | 56 | `candidate_for_schema_registry` | 68<br>30<br>69 |
| 50 | `全校博士专业` | `school_phd_programs` | `long_text` | 35.1% | 387 | `candidate_for_schema_registry` | 材料科学与工程；材料与化工(专)；测绘科学与技术；大气科学；地理学；地球物理学；地质学；电子科学与技术；电子信息(专)；法学；工商管理学；公共管理学；公共卫生(专)；公共卫生与预防医学；国家安全学；核科学与技术；护理学；化学；环境科学与工程<br>电子信息(专)；法律(专)；法学；工商管理学；公共管理学；管理科学与工程；管理科学与工程；国家安全学；化学；计算机科学与技术；纪检监察学；考古学；理论经济学；马克思主义理论；农林经济管理；社会学；世界史；数学；统计学；外国语言文学；物理学<br>安全科学与工程；材料科学与工程；材料与化工(专)；城乡规划学；大气科学；电气工程；电子科学与技术；电子信息(专)；动力工程及工程；法律(专)；法学；风景园林学；工商管理学；工业工程；公共管理学；管理科学与工程；光学工程；航空宇航科学与技术； |
| 51 | `2024招生章程` | `admission_brochure_2024` | `long_text` | 100.0% | 1553 | `candidate_for_schema_registry` | https://gaokao.chsi.com.cn/wap/zszc/viewZszc?schId=1&infoId=5482677367<br>https://gaokao.chsi.com.cn/wap/zszc/viewZszc?schId=2&infoId=5480559068<br>https://gaokao.chsi.com.cn/wap/zszc/viewZszc?schId=3&infoId=5482330956 |
| 52 | `软科评级` | `soft_science_rating` | `enum_or_category` | 38.1% | 4 | `candidate_for_schema_registry` | A<br>A+<br>B+ |
| 53 | `软科排名` | `soft_science_ranking` | `number` | 38.1% | 404 | `candidate_for_schema_registry` | 4<br>1<br>3 |
| 54 | `学科评估` | `discipline_evaluation` | `enum_or_category` | 18.2% | 33 | `candidate_for_schema_registry` | 四轮：A+；五轮：A+<br>四轮：A；五轮：A+<br>四轮：B+；五轮：A- |
| 55 | `专业水平` | `major_level` | `enum_or_category` | 30.8% | 185 | `candidate_for_schema_registry` | 国一<br>国一/未名学者中国语言文学拔尖学生培养基地<br>国一/未名学者历史学拔尖学生培养基地 |
| 56 | `本专业硕士点` | `major_master_program` | `enum_or_category` | 32.1% | 269 | `candidate_for_schema_registry` | 外国语言文学； 教育（专硕）； 翻译（专硕）<br>外国语言文学； 翻译（专硕）<br>博物馆（专硕） |
| 57 | `本专业博士点` | `major_phd_program` | `enum_or_category` | 14.0% | 193 | `candidate_for_schema_registry` | 外国语言文学； 教育（专博）<br>外国语言文学<br>考古学 |

## Important Consequence

Some user preferences that were previously treated as missing may actually have candidate columns:

- `公办` may map to `公私性质` after verification.
- `学校好一点` or `学校名气` may map to `院校水平`, `院校排名`, `院校标签`, or `软科排名`, but only after policy review.
- `城市不要太差` or `偏远` may map to `城市水平标签`, but only after confirming the semantics.
- `中外合作` still needs careful handling; it should not be inferred from free text until a dedicated or verified derived field exists.

The next step is not to execute all these fields automatically. The next step is to review and promote safe fields into the schema registry with allowed operators and trace notes.
