# Computational Intelligence Work · Tablut

本项目在 9×9 Tablut 棋盘上研究非对称攻守搜索。攻方先行，目标是擒王；守方要让王抵达边线。正式对局每方整局 60 秒。规则与终局以 [Python 裁判](required_files/Tablut.py) 为准。

## 当前版本

正式参赛入口为 [Team01.py](submission/Team01.py)，执攻使用动态反驳，执守使用重训估值。两侧均保留原时钟。组件按 Python 3.12 的单文件接口封装。[英文报告](submission/Report01.pdf)与[可编辑稿](phase2/report/Report01.html)使用暂定编号 01，团队分工按要求留空。

攻方时钟另做了一次冻结对照。候选从 128 局开发棋谱中估计给定已走手数后的剩余己方回合，其他参数沿用原版。每组 8 个新种子，对 Kurz 与新守法 RouteAB 共 32 局。第 81 手起，可避免的三手内强败由 2/90 次攻方决策降至 1/111 次；总积分由 24/32 降至 22/32，未达到赛前晋级条件。[预定赛程和判据](phase2/tail_clock_plan.json) · [结果](phase2/tail_clock_summary.json)

实验基线为 [护子版](phase2/attacker.py)。它用 PUCT 搜索，结合逃线、子力与守方应对评估候选走法。[重训版](phase2/attack_candidates.py) 是挑战者，更新了估值权重并增加短程擒王复核。两版的[自弈估值模型](phase2/value_model.py)都使用 11 项输入（含常数项）做三分类逻辑回归，输出守胜、和棋和攻胜概率。作业目录中的 Team01 与实验基线有各自的入口。

## 本地复盘

下载项目后直接打开 [棋盘分析/index.html](棋盘分析/index.html)。选择「完整引擎 · kurz」下重训版种子 12022 的棋谱，即可查看第 115 手前的局面、实战选择和可行补防。浏览器复盘模式的每手分析时限与正式比赛的整局时钟分开设置。

## 冻结版本的对局结果

下表均为我方执攻的胜／和／负。同一行内两版配对使用相同种子。

| 守方 | 每版局数 | 护子版 | 重训版 |
|---|---:|---:|---:|
| tLut 估值，一手贪心 | 4 | 3／0／1 | 4／0／0 |
| tLut 估值，easyAI 多手搜索 | 4 | 3／1／0 | 4／0／0 |
| Sinclair UCT | 4 | 4／0／0 | 4／0／0 |
| easyAI | 4 | 3／0／1 | 2／1／1 |
| 二代 PUCT | 4 | 1／0／3 | 0／0／4 |
| Randy Li 原生搜索 | 8 | 8／0／0 | 8／0／0 |
| Philipp Kurz 原生搜索 | 8 | 4／1／3 | 5／1／2 |

前五行来自[跨策略实验](phase2/open_field_summary.json)。后两行使用两位作者自己的 Java 搜索和估值，按作业规则适配，以全新种子 12021–12028 进行了 [32 局比赛](phase2/native_field_matches.json)。[逐手复核](phase2/native_field_review.json)发现，Kurz 兑现了重训版两次、护子版一次可避免的短程漏防。三次落子前攻方均剩不到 0.6 秒。同局面从空树给 1,600 次访问后，两版均能避开短程强败。长局尾段用时值得单独检验，现有对局量仍不足以断定哪版整体更强。

## 复现实验

[动态反驳实验](phase2/refutation_summary.json)冻结护子版估值、时钟和 23% 复核预算。8 个新种子分别对 Kurz 和二代 PUCT，固定版得到 14/32 分，动态版得到 26/32 分。动态版只在 Kurz 13405 第 27 手直接推翻原选并经官方枚举确认避开三手强败；两版在这组配对中都赢了。该批积分差不能直接归因于这次改手。运行 `python -B phase2/refutation_field.py` 可补齐对局，`python -B phase2/refutation_report.py` 可重算报告和本地棋盘数据。

从仓库根目录运行 `python -B phase2/native_field_review.py`，可用保存的棋谱重算漏防报告和本地棋盘数据。运行 `python -B phase2/native_field.py` 可补齐缺失的正式对局；脚本会跳过已有记录。要独立重跑整批比赛，可在另一份检出中先移走 `phase2/native_field_matches.json`。实验使用 Python、NumPy 和 JDK 17，Java 工具可通过 JAVA_HOME 指定；限时对局会随机器负载变化。

实验对手的来源和固定版本见[跨策略报告](phase2/open_field_summary.json)及[原生引擎报告](phase2/native_field_review.json)。第三方引擎位于 phase2/opponents，供对照实验使用。
