# RS06 固定 Armature 的均衡 RMS、LOTO 辨识方案与阶段结果

本文冻结 2026-08-16 确认的方案，并记录 2026-08-17 的实现与正式运行状态。根目录
`identify-balanced` CLI、周期增强 actuator、均衡 RMS、Kd–viscous profile、armature
条件重拟合、11 折 LOTO、W&B 和断点恢复已实现。正式运行的主 CMA、冻结
R01--R13 评价和主参数灵敏度已经完成；LOTO 完成 R01--R05 后因主机重启中断，
按当前决定暂不恢复。纯 Python 回归测试、Isaac
截断全链烟雾测试、同目录 resume，以及 1 候选/8 候选并行一致性均已通过。
截断烟雾输出不是物理辨识结果；只有不含 `--quick/--max-samples` 的正式运行
才能用于参数结论。

## 1. 目标与结论边界

本阶段首先追求一组对主动台架具有稳定预测能力的 simulator-effective 参数，而不是
强迫每个 DCMotorCfg 字段都成为唯一物理真值：

1. 固定无法由当前数据辨识的输出轴侧 armature 先验；
2. 扩展 static、dynamic/static ratio 和 viscous 搜索范围；
3. 使用 R01–R11 选择一组使逐轨迹 position RMS 更均衡的三摩擦参数；
4. 参数冻结后才评价 R12/R13；
5. 对 R01–R11 做 leave-one-trajectory-out（LOTO），检查参数和预测是否依赖某一条
   轨迹；
6. 分别报告“轨迹预测有效”“给定 armature 后条件可辨识”“不可辨识”。

不能以“让参数离开边界”为优化目标。只有在足够宽的物理范围内自然出现、并能被
restart/profile/LOTO 重现的内部最优才是有效证据；再次命中边界本身也是辨识结论。

## 2. 固定 Armature 先验

当前先验来自 `scripts/initial_parameter_caculator.py` 的厚壁等效钢圆柱模型：

- 轴向长度 `h=0.025 m`；
- 外半径 `r_o=0.015 m`；
- 内半径 `r_i=0.005 m`；
- 等效密度 `rho=7850 kg/m³`；
- 减速比 `N=9`，定义为电机转速/输出轴转速。

计算式为：

```text
m       = rho*pi*h*(r_o²-r_i²)                 = 0.12331 kg
J_rotor = 0.5*m*(r_o²+r_i²)                    = 1.54134e-5 kg·m²
J_out   = J_rotor*N²                           = 1.2484886e-3 kg·m²
```

因此正式搜索固定：

```python
armature = 1.2484886e-3  # output-joint kg·m²; geometry prior, not fitted
```

该模型没有准确表示磁钢、槽、铜、轴和减速器内部转动件。最终报告必须标为 9:1
输出侧折算几何先验，并额外在 `0.5×/1×/2×` armature 下重新拟合摩擦，传播这一
先验的不确定性。CAD 中的负载刚体惯量已经由 PhysX 建模，不能再次计入 armature。

## 3. 周期阻力前置模型与分层速度门禁

三摩擦 CMA 之前先冻结一个独立辨识的周期增强项，不能再让 DCMotorCfg 的摩擦或
armature 吸收已确认的 k=126 位置周期残差。两次连续正反转 session 录制了
`0.05/0.10/0.20/0.50/1.0/2.0 rad/s`，均为 Kp/Kd=`50.0/3.38`、50 Hz、每档每向
三圈。第二次 session 共 `11,090` 帧、steady `5,994` 帧，无 NaN/缺 sample index；
steady 中只有一个 `34.005 ms` 间隙。该孤立间隙两侧样本从角域拟合中剔除，不插值，
但不因一处间隙否定其余数百个周期；这套结构数据不按普通 R 轨迹的连续时域规则处理。
其中 2 rad/s 使 k=126 的实测时间频率约为 39.2 Hz，超过 50 Hz 反馈的
25 Hz Nyquist 频率，因此在数值分析入口就丢弃，不作摩擦拟合、周期幅值验证或图上诊断点。

正反方向的 k=126 sin/cos 系数必须先做**向量半和**，再计算共同周期项的幅相。禁止
先计算两个幅值再取算术平均，否则正反相位存在动态偏移时会高估位置共同项。正式
calibration 只使用 0.05/0.10 rad/s 的 rotations 0–1：

```python
tau_periodic = -0.554577029 * sin(126.0*q + 2.563279669)  # joint-side N·m
```

rotation 2 held-out 得到 `A=0.569449 N·m`（相对 `+2.682%`）、phase 变化
`-0.01133 rad`。`k=126` 固定，不进入 CMA；A/phase 标记为当前编码器零位、上电控制器
及电流折算下的 quasi-static effective 先验。仿真必须分别保存：

```text
tau_controller = DCMotor controller applied effort   # 与实机 torque feedback 对比
tau_joint_net  = tau_controller + tau_periodic       # 送入关节动力学
```

0.20–1.0 rad/s 只做结构/观测动态验证。k=126 对应的时间频率从约 3.9 Hz 增至
19.8 Hz；1.0 rad/s 已接近 50 Hz 采样的 25 Hz Nyquist，其 torque 周期幅值也不得
用于覆盖准静态 A。

丢弃 2 rad/s 后，正反 torque offset 的五个可用速度观测为：

```text
speed [rad/s] : 0.05    0.10    0.20    0.50    1.00
offset [N·m]  : 0.1493  0.1634  0.1564  0.1135  0.0450
```

用 0.05–1.0 rad/s 五点拟合得到
`F=0.17054 N·m, B=-0.12564 N·m/(rad/s)`、RMSE=`0.00877 N·m`。甚至只使用
0.05–0.50 rad/s 仍得到 `B=-0.10211`，说明在可用采样范围内就已不支持
直接从 torque offset 解释出正黏性摩擦。

最保守的 0.05/0.10/0.20 rad/s 三点得到
`F=0.15272 N·m, B=0.03233 N·m/(rad/s)`，但相比 `B=0、F=0.15637 N·m`，RMSE
仅从 `0.00577` 降至 `0.00543 N·m`，且两两斜率符号不一致，仍不足以识别 viscous。
五点负斜率是 Kd/target 帧语义、电流 torque 估计或滤波存在速度相关项的门禁失败，
不能写入 `viscous_friction`。因此：

- 该数据集独立命名为 `constant_speed_structural`，不作为 76k 原始样本的普通 R14；
- phase-bin、每圈、每速度等权汇总保存，periodic calibration 与 held-out 圈严格分开；
- 低速 `0.15–0.16 N·m` 只作为 moving-resistance 量级诊断，不直接初始化两个摩擦字段；
- 2 rad/s 在分析入口硬排除，1 rad/s 也只进入控制器动态诊断；
- 正式四字段模型必须先通过 `F>=0, B>=0` 被动物理门禁；失败时报告 controller/torque
  observation mismatch，不允许优化到负 viscous；
- periodic 参数冻结后才运行 R01–R11 三摩擦 CMA 和 armature sensitivity。

## 4. 三摩擦搜索空间

使用本机 Isaac Lab 2.3.2 / Isaac Sim 5.1 的实际字段：

```text
theta = [friction, dynamic_friction_ratio, viscous_friction]
dynamic_friction = friction * dynamic_friction_ratio
```

推荐宽范围：

```yaml
friction: [0.02, 0.60]                 # N·m
dynamic_friction_ratio: [0.005, 1.0]  # dimensionless
viscous_friction: [1.0e-4, 0.8]       # N·m/(rad/s)
```

三维均使用仿射归一化 log 坐标，保持参数为正并约束
`dynamic_friction <= friction`。armature、真实 Kp/Kd=`50.0/3.38`、理论电机限幅与
solver 限制保持固定。五个可用速度的 torque offset 不能作为 viscous 初值；若 position 主导
结果继续命中 `1e-4` viscous 或最低 dynamic ratio，不再自动扩界，而是报告当前主动
数据只支持某个组合阻力，或固定 Kd/控制器结构与实机不一致。

## 5. 均衡 Position RMS 目标

所有选优只使用 R01–R11，并保持每条轨迹等权。定义：

```text
e_i = RMSE(q_sim_i - q_real_i)
r_i = e_i / 0.02 rad
```

主目标建议为：

```text
J_position = 0.6 * mean_i(r_i)
           + 0.4 * mean(largest_three(r_i))
J_select   = J_position + 0.03*L_velocity
J_torque_diagnostic = 0.005*L_torque
```

`largest_three` 相当于小样本 top-tail/CVaR，用于阻止 R06/R11 等困难轨迹被平均值
掩盖。velocity 反馈抖动较大，因此只作弱约束。torque 虽是已含 9:1 的输出轴侧电流
折算值，但五速度被动物理门禁失败，正式最优参数**不得由 torque 选择**；`0.005` 只
生成对照分数和图。如果后续建立并验证 torque observation model，才允许重新启用非零
选优权重。正式实现应允许配置 top-k 和权重，并保存 position-only、v、torque 三个
独立分项。

R12/R13 不进入参数选择、停止、边界扩展或 Pareto 点选择。若未来将 R01–R13 全部
用于 calibration，必须新增独立验证轨迹，不能继续称 R12/R13 为 validation。

## 6. 指标与有效性判据

逐 R01–R13 输出：

- position RMS、MAE、raw max absolute error 和 P99 absolute error；
- velocity/torque 的相同指标；
- NRMSE：

```text
NRMSE_i = RMSE_i / max(P95(q_real_i)-P5(q_real_i), 0.02 rad)
```

该分母下限避免 R01 等近静止轨迹因运动范围接近零而产生无穷或无意义 NRMSE。

汇总分别输出：

- R01–R11 fit 的 median、P90、max position RMS；
- fit 中 `RMS <= 0.02 rad` 的轨迹数；
- R12、R13 各自指标和 validation max；只有两个 validation 时不把 P90 伪装成
  稳健统计；
- 相对当前正式模型的逐轨迹 paired 改善/恶化；
- 频响增益、相位、coherence 和残差随 q/v/方向的结构。

参数状态按以下规则分类：

- `conditionally_identified`：固定 armature/Kp/Kd/模型结构后，多个 restart 收敛到
  相同内部区域，profile 在两侧明显上升，LOTO 稳定且 validation 不恶化；
- `weak_or_combination_only`：单字段变化大，但
  `F_dynamic*sign(v)+B*v` 在观测速度范围内预测带稳定；
- `not_identifiable`：profile 平坦、半倍/双倍 loss 变化不超过 1%、命中边界、
  `|corr|>0.95` 或 LOTO 参数跨数量级变化。

不得只报告 Hessian 点估计；边界存在时 Hessian/伪逆置信区间不能覆盖参数删失语义。

在三摩擦主优化之前/之后都运行 Kd–viscous 二维诊断：Kd multiplier 使用
`[0.90,0.95,1.00,1.05,1.10]`，viscous 使用 20–30 个 `[1e-4,0.8]` log 点。正式模型
仍固定真实配置 Kd=`3.38`；该 profile 只判断 position 最优谷是否沿 `Kd+B` 延伸。
若 ±5% Kd 变化即可把 viscous 从一端推到另一端，则将 viscous 标为
`weak_or_combination_only`，不能宣称其独立物理有效。五个可用速度的 torque
offset 的负斜率约 `-0.1256 N·m/(rad/s)`，仅相当于 Kd 的约 3.7%，正说明这个诊断
不可省略。

## 7. Leave-One-Trajectory-Out

完整三摩擦结果得到后，对 `i in R01..R11`：

1. 从 fit 中移除 `i`；
2. 从全量最优 warm-start，用剩余十条执行一次 15–20 代局部 CMA；
3. 冻结参数，分别评价剩余十条、被移除的 `i`、R12 和 R13；
4. 保存参数影响量：

```text
I_i = ||log(theta_without_i) - log(theta_full)||_2
```

同时报告被移除轨迹的 hold-out RMS、其相对全量模型的变化、fit max RMS、validation
变化和边界命中。LOTO 是稳定性诊断，不是自动删数据程序。

LOTO 每折只重拟合三摩擦，k/A/phase 使用上游 structural calibration 的冻结值，禁止
针对被移除的 R 轨迹重新调整周期项。另做 A=`0.50×/1.00×/1.50×` 与 phase
`±0.02 rad` 的小型敏感性，传播 controller-effective 周期先验的不确定性。

只有存在数据损坏、饱和/接触、配置不一致，或该工况被明确排除出部署范围时才允许
移除轨迹。R05（匀速摩擦）、R06（加速/惯量）、R11（宽频）即使难拟合也具有关键
辨识价值；R13 是 validation，本来就不在 fit 中。若有效数据之间冲突，应报告模型
结构不足，并可另给“有限部署域 core model”，但必须保留 full-domain 失败结果。

## 8. 预算、时间和恢复

本机 RTX 5090 上，现有 population 20、R01–R11 三摩擦正式运行实测每代中位数
约 `50.05 s`。建议预算：

| 阶段 | 预算 | 预计墙钟时间 |
|---|---:|---:|
| 两个匀速 session 审计/周期冻结 | 角域离线分析 | <1 min |
| Kd–viscous 二维诊断 | 5 × 20–30 点，批量 | 15–35 min |
| 宽范围主优化 | 4 restart × 40 代 | 2.2–2.7 h |
| 冻结 R01–R13 指标/图 | 1 次 | 10–20 min |
| 11 折 LOTO | 每折 1 restart × 15–20 代 | 2.3–3.3 h |
| armature 0.5×/1×/2× 敏感性 | 两个额外局部重拟合 | 0.5–1 h |
| profile/汇总 | — | 15–30 min |

实用版总运行时间约 `5.8–8.1 h`。该估计要求 `--num-envs 20`，使每代
population 20 在一个物理 timeline 中完成；`--num-envs 4` 会把每代拆成 5 批，本机
preflight 已测得约 `14.9 h` 的完整链估计，不应用于正式运行。Kit 当前还报告
CPU profile 为 `powersave`，所以正式运行前应用 preflight 重测，不要盲目套用时间表。
若每折使用 2 restart ×30 代做确认，总时间约
`11.3–13.6 h`。实现时主优化和每个 fold 都必须有独立原子 checkpoint、固定 seed、输入
哈希和可恢复 progress；不要并行创建 11 倍物理环境导致 PhysX/CPU 反而变慢。

正式启动命令：

```bash
mkdir -p logs
set -o pipefail
PYTHONUNBUFFERED=1 ../isaacsim/bin/python rs06_tool.py identify-balanced \
  --config rs06_balanced_rms.yaml \
  --seed 20260813 \
  --num-envs 20 \
  --output-dir outputs/rs06_balanced_rms_run01 \
  --wandb-mode online \
  --wandb-project rs06-system-identification \
  --headless 2>&1 | tee logs/rs06_balanced_rms_run01.log
```

异常关机后使用完全相同的 config/seed/并行容量恢复：

```bash
PYTHONUNBUFFERED=1 ../isaacsim/bin/python rs06_tool.py identify-balanced \
  --config rs06_balanced_rms.yaml \
  --seed 20260813 \
  --num-envs 20 \
  --resume outputs/rs06_balanced_rms_run01 \
  --wandb-mode online \
  --headless
```

截至 2026-08-17，本次正式结果目录的 LOTO 停在 R06 第 7/20 代。checkpoint 完整且
技术上仍可恢复，但当前决定是**不恢复、不继续 R06--R11 LOTO**，先使用已经完成的
主优化、冻结验证和前五折证据作模型判断。因此上面的命令只作为可恢复性记录，不是
当前建议执行的命令。

## 9. 已实现输出

独立结果目录至少包含：

```text
balanced_rms_config.yaml
constant_speed_structural/combined_analysis.json
constant_speed_structural/periodic_calibration.json
constant_speed_structural/passive_friction_gate.json
kd_viscous_profile_pre.json/.png
kd_viscous_profile_post.json/.png
periodic_prior_sensitivity.json/.png
friction_identifiability.json
friction_identifiability_profiles.png
optimization_summary.json
paired_position_improvement.json
best/parameters.json
best/DCMotorCfg.py.txt
best/RS06AugmentedMotorCfg.py.txt
best/trajectory_metrics.csv
best/aggregate_rms_metrics.json
best/frequency_response.json
loto/summary.json
loto/fold_R01.json ... fold_R11.json
armature_prior_sensitivity.json
parameter_validity.json
model_interpretation.json
checkpoints/
reproduce_command.txt
```

最终交付必须明确回答：哪一组参数在目标部署轨迹上预测最好；哪些字段只是在固定
先验下条件有效；哪些字段只能确定组合阻力；哪些字段仍不可辨识。

本地进度看 `workflow_status.json`、`progress.json`、
`balanced_friction_history.csv` 和 `loto/summary.json` 的 `completed_fold_count`。W&B 记录
每代的 global/generation best、三个摩擦参数、逐轨迹 position RMS 和最终
fit median/P90/max/达标数。

## 10. 2026-08-17 正式运行结果快照

### 10.1 完成状态与可复现性

正式结果位于：

```text
outputs/rs06_balanced_rms_run01
```

当前没有 Isaac 或辨识进程在运行。各阶段状态如下：

| 阶段 | 状态 | 证据 |
|---|---|---|
| 输入/资产审计 | 完成 | `data_audit.json`、`run.json` |
| 单环境/并行一致性 | 完成且通过 | q/v/torque/loss 差异均为 0 |
| 周期项冻结 | 完成 | `constant_speed_structural/periodic_calibration.json` |
| Kd–viscous 前置 profile | 完成 | `kd_viscous_profile_pre.json` |
| 4-restart 主 CMA | 完成 | 3000 次候选评价、150 代 |
| R01--R13 冻结评价 | 完成 | `best/metrics.json`、图和频响 |
| 三摩擦 profile/近优候选分析 | 完成 | `friction_identifiability.json` |
| 周期 A/phase 敏感性 | 完成 | `periodic_prior_sensitivity.json` |
| Kd–viscous 后置 profile | 完成 | `kd_viscous_profile_post.json` |
| LOTO | 有意暂停 | R01--R05 完成；R06 checkpoint 停在 7/20 代 |
| armature 条件重拟合与最终 validity 汇总 | 未运行 | 原工作流位于完整 LOTO 之后 |

`run.json` 记录的关键版本为 Isaac Sim `5.1.0.0`、Isaac Lab 源码 `2.3.2`
commit `3e73d6dd79080fd7632488c061052a6edd52e230`、`cma 4.4.4`。资产组合哈希为
`61c1ade463c3be8afcc6c57741f511c85eb29db5a44c6716ed877884d38313d0`，manifest
哈希为 `f708ef5d1204c5804124d1dfc8f9abce64f3260b60f2e6c235cb4cea2459b325`。
并行一致性检查以 1/8 环境比较，四项差异均为零；轴向运动学检查 correlation 为
`0.999951`，因此以下差异不是并行批处理或轴符号错误造成的。

### 10.2 当前预测最优参数及正确使用方式

主 CMA 只用 R01--R11 选优，R12/R13 没有参与选择。当前冻结参数是：

```python
armature         = 1.2484886e-3       # kg m^2，固定物理先验，未辨识
friction         = 0.3095849600       # N m
dynamic_friction = 0.00174159893      # N m
viscous_friction = 0.000100881924     # N m/(rad/s)

periodic_order        = 126            # 冻结独立标定
periodic_amplitude_nm = 0.5545770295
periodic_phase_rad    = 2.5632796694
```

这组位置指标属于 **PeriodicDCMotor**，必须使用
`best/RS06AugmentedMotorCfg.py.txt` 中的 `PeriodicDCMotorCfg` 才能复现。单独复制
`best/DCMotorCfg.py.txt` 会漏掉周期力矩，不能把下表当作普通标准 `DCMotorCfg` 的效果。
该结果目录和 checkpoint 应原样保留；普通 DCMotor 三摩擦搜索必须使用另一个配置与
输出目录。

### 10.3 R01--R13 冻结位置指标

| ID | split | RMS [rad] | NRMSE | MAE [rad] | max [rad] | P99 [rad] |
|---|---|---:|---:|---:|---:|---:|
| R01 | fit | 0.002308 | 0.0058 | 0.001543 | 0.010418 | 0.007030 |
| R02 | fit | 0.005027 | 0.0530 | 0.002685 | 0.021136 | 0.019218 |
| R03 | fit | 0.013419 | 0.0068 | 0.005705 | 0.089413 | 0.065293 |
| R04 | fit | 0.002433 | 0.0069 | 0.001562 | 0.011458 | 0.009499 |
| R05 | fit | 0.020441 | 0.0107 | 0.011905 | 0.070225 | 0.064159 |
| R06 | fit | 0.030345 | 0.0191 | 0.020575 | 0.100240 | 0.093356 |
| R07 | fit | 0.008748 | 0.0131 | 0.006656 | 0.024275 | 0.021006 |
| R08 | fit | 0.008891 | 0.0135 | 0.006771 | 0.025337 | 0.022147 |
| R09 | fit | 0.003426 | 0.0258 | 0.002351 | 0.014467 | 0.011186 |
| R10 | fit | 0.008314 | 0.0222 | 0.006404 | 0.028567 | 0.023182 |
| R11 | fit | 0.021924 | 0.0377 | 0.016628 | 0.052900 | 0.046580 |
| R12 | validation | 0.012686 | 0.0087 | 0.009584 | 0.037209 | 0.032217 |
| R13 | validation | 0.025408 | 0.0329 | 0.020119 | 0.052512 | 0.050365 |

汇总为：

| split | median RMS | P90 RMS | max RMS | `RMS <= 0.02 rad` |
|---|---:|---:|---:|---:|
| fit R01--R11 | 0.008748 | 0.021924 | 0.030345 | 8/11 |
| validation R12--R13 | 0.019047 | 不报告（仅 2 条） | 0.025408 | 1/2 |

相对本次初始参数，fit median 改善 `20.1%`，P90 改善 `4.0%`，max 改善 `7.0%`；
validation median 改善 `11.5%`，validation max 改善 `9.4%`。13 条中 12 条 RMS
下降，只有 R02 从 `0.004620` 增至 `0.005027 rad`，但仍远低于阈值。最难的工况仍是
R06，其次是 R11、R05；validation 的 R13 也未达到 0.02 rad。优化改善了整体预测，
但没有增加达到阈值的轨迹数（fit 仍为 8/11，validation 仍为 1/2）。

### 10.4 频响与 torque 诊断

位置频响与时域 RMS 的结论一致：R07/R08 的 Welch H1 position 中位绝对增益误差
分别约 `0.123/0.074 dB`，中位绝对相位误差约 `5.42/5.48 deg`，实机 position
coherence 中位数分别为 `0.994/0.999`。独立 R12 sine bank 的 position 中位绝对
增益误差约 `0.015 dB`、相位误差约 `5.15 deg`；在 2.9 Hz 处相位误差约
`-7.28 deg`。这说明幅值跟踪很好，但存在随频率增加的额外相位滞后，单靠三摩擦
不能解释。

torque 没有参与选优。冻结结果中，把 simulator `applied_effort` 仿射映射到实机
电流折算 torque 得到 scale=`0.4453`、bias=`0.0629 N m`、R²=`0.490`；最大相关还
出现在 `-1` 个 50 Hz 帧（`-20 ms`）。因此 torque 图可用于发现结构和时序问题，
不能用来证明当前摩擦参数是物理真值。

### 10.5 为什么当前三摩擦不是有效的唯一辨识值

四个独立 restart 得到：

| restart | score | friction | dynamic_friction | viscous_friction |
|---:|---:|---:|---:|---:|
| 0 | 0.875454 | 0.309585 | 0.001742 | 0.0001009 |
| 1 | 0.877793 | 0.040039 | 0.000261 | 0.0001029 |
| 2 | 0.875584 | 0.282969 | 0.001480 | 0.0001001 |
| 3 | 0.877770 | 0.041766 | 0.000217 | 0.0001011 |

restart 0/2 与 1/3 落在两个不同 static-friction 区域；`friction` 相差约 `7.7×`，
目标只差约 `0.27%`。主最优在 restart 0 的第 4 代已经出现，之后增加计算没有消除
多解性。fit-only profile 进一步显示：

- friction 从 `0.155` 到 `0.600 N m`，相对 loss 变化均不到 `0.72%`；
- dynamic/static ratio 减半或翻倍，loss 变化不到 `0.06%`，最小值在允许的更低侧；
- viscous 减半/翻倍，loss 变化约 `0.011%`，且最小值在下界；
- 3000 个 CMA 候选中有 2823 个位于 archive 最优的 1% 以内。

所以当前可支持的结论是“存在一大片参数区域具有相近的位置预测能力”，不是
“三摩擦已被精确辨识”。`friction=0.3096` 只是当前均衡目标的最优代表点；
`dynamic_friction` 和 `viscous_friction` 应标为下界删失/弱不可辨识。

### 10.6 Kd、viscous 和周期先验的归因

前置和后置 Kd–viscous profile 都显示，对 Kd multiplier
`[0.90,0.95,1.00,1.05,1.10]` 的每一行，最佳 viscous 都是搜索最低值 `1e-4`。
后置 profile 的各行最优 score 为：

```text
Kd multiplier : 0.90    0.95    1.00    1.05    1.10
best score    : 0.5821  0.7194  0.8755  1.0392  1.2059
best viscous  : 1e-4    1e-4    1e-4    1e-4    1e-4
```

这不是 viscous 上界不足，而是固定 `Kd=3.38` 下 simulator-effective 阻尼已经偏大；
正的 `viscous_friction` 只能继续增加阻尼，无法补偿这一差异。下一轮不应继续扩大
viscous 上界以寻找内点，也不能把允许负 viscous 当作修复。应把它标为
`weak_or_combination_only`，并把 Kd/驱动器离散控制和反馈滤波不一致列为模型误差。

周期项敏感性在 `A=1.0×、phase=-0.02 rad` 得到最低 score `0.875148`，与冻结 phase
的 `0.875454` 只差约 `0.035%`；A=`0.5×` 和 `1.5×` 的最低 score 分别约
`0.8946`、`0.9446`。这支持独立标定的 A 量级，但不能把 A/phase 当成精确、跨上电
零位不变的物理常数。

### 10.7 已完成五折 LOTO 能说明什么

| 移除 | friction ratio | dynamic ratio | viscous ratio | 被移除轨迹 RMS 变化 [rad] | fit max | validation max |
|---|---:|---:|---:|---:|---:|---:|
| R01 | 0.864 | 0.772 | 1.003 | +0.000003 | 0.030335 | 0.025402 |
| R02 | 0.087 | 0.078 | 1.015 | +0.001188 | 0.030310 | 0.025385 |
| R03 | 0.865 | 0.775 | 1.011 | -0.000003 | 0.030335 | 0.025402 |
| R04 | 1.430 | 1.755 | 1.624 | +0.000174 | 0.030374 | 0.025448 |
| R05 | 1.422 | 1.324 | 1.008 | +0.000005 | 0.030364 | 0.025435 |

五折中，fit median/P90/max 和 validation max 几乎不变，但参数可以明显变化；移除
R02 时 friction 甚至从 `0.3096` 降到 `0.0268 N m`。这再次证明“预测对参数变化不
敏感”。R02 对选择哪个等效 friction 模态有影响，但它本身的 hold-out RMS 仍只有
`0.00622 rad`，没有数据损坏证据，不能据此删除。现有五折已经足以支持弱可辨识结论；
暂停其余六折不会改变主优化和冻结 validation 的有效性，但意味着不能声称完成了
11 折稳定性验证。

### 10.8 当前结论及下一轮边界原则

1. **预测层面：部分有效。** 当前 PeriodicDCMotor 对大多数轨迹有较好 position
   预测，宽频 position 幅值也准确；R05/R06/R11/R13 仍暴露模型误差。
2. **参数层面：三摩擦未唯一辨识。** armature 是固定几何先验；static friction
   只有等效多解，dynamic 与 viscous 是近零方向的下界删失值。
3. **当前最主要限制不是搜索范围太小。** 更大的 viscous 上界没有意义；更低的下界
   只会把删失点继续推向零，不会自动产生可信内点。
4. **LOTO 暂停是合理的。** 现有五折已经揭示参数不稳定而预测稳定；先分析模型结构
   比消耗约 5 个小时完成剩余折更有价值。
5. **普通标准 DCMotor 必须独立运行。** 它不含周期项，其三摩擦最优区域不能直接从
   本结果抄取。下一步应结合已有普通 DCMotor 结果和本节的 near-zero 证据，先做低成本
   profile/grid，再给 CMA 设置紧凑边界；不能为了获得“非边界参数”人为裁掉真正的
   低阻尼区域。

在确认普通模型的低成本 profile 之前，本文件不冻结新的普通 DCMotor 边界。初步边界
方向是：保留 fixed armature；显著缩小 viscous 上界；dynamic/static ratio 覆盖接近零
的区域；friction 仍需覆盖至少当前两个等效模态。正式数值将在普通模型 profile 后写入
独立配置，避免用 PeriodicDCMotor 的参数空间替代普通 `DCMotorCfg` 的证据。

### 10.9 低速 Stribeck 摩擦假设

#### 观测与假设等级

当前五个可用正反匀速观测的方向奇对称 torque offset 为：

```text
speed [rad/s] : 0.05    0.10    0.20    0.50    1.00
offset [N m]  : 0.1493  0.1634  0.1564  0.1135  0.0450
```

从约 `0.10` 到 `0.50 rad/s`，观测阻力随速度升高而下降。一个合理解释是：该速度范围
仍位于 Stribeck 区域，低速摩擦正在从起动/保持水平下降到运动库仑摩擦平台，并且下降
项暂时大于正黏性摩擦的增量。令 `r_f` 表示沿运动方向为正的阻力需求，则可写成：

```text
r_f(v)       = sign(v) * [F_c + (F_s-F_c)*exp(-(abs(v)/v_s)^alpha)] + B*v
tau_passive  = -r_f(v)
```

其中 `F_s >= F_c >= 0`、`v_s > 0`、`alpha > 0`、`B >= 0`。在正速度侧：

```text
d r_f / d v
  = B - (F_s-F_c)*alpha/v_s*(v/v_s)^(alpha-1)*exp(-(v/v_s)^alpha)
```

所以即使物理黏性系数 `B` 非负，低速总摩擦的局部斜率仍可为负。不能因为观测到
负斜率，就把 Isaac 的 `viscous_friction` 设置成负数。

该解释与当前 PeriodicDCMotor 优化现象相容：优化器选择较大的 `friction` 表示
起动/保持阈值，同时把 `dynamic_friction` 压到很低、把 `viscous_friction` 压向零。
这可能是在用 PhysX 的静态到动态切换，近似真实电机中连续的 Stribeck 下降，而不仅仅
是“真实运动摩擦接近零”。

目前必须把它标记为**待验证假设，而不是已辨识结论**。现有证据仍存在以下混杂：

- torque 是已折算到输出轴侧的电流估计，不是独立力矩传感器；
- 实机内部电流/速度滤波、控制周期和 torque feedback 时序未知；
- 固定 Kd 与 simulator-effective damping 已表现出明显失配；
- 50 Hz 反馈会衰减或混叠高速位置周期项；1 rad/s 只适合作控制器动态诊断，
  不能覆盖准静态摩擦曲线；
- 0.05 到 0.10 rad/s 的 offset 先上升后下降，不符合一条无噪声、严格单调的简单
  Stribeck 曲线，可能还包含速度估计量化、stick-slip、周期项残留或温度变化。

#### 标准 DCMotorCfg 的表达能力

本机 Isaac Lab 2.3.2 / Isaac Sim 5.1 的公开 API 文档与实际写入路径说明：

```text
at rest : friction defines the maximum effort preventing motion
moving  : tau = -sign(v) * (dynamic_friction + viscous_friction*abs(v))
```

`dynamic_friction` 在运动后是常数，`viscous_friction` 是非负速度比例项。标准
`DCMotorCfg` 没有 `v_s`、`alpha` 或连续 Stribeck 插值参数；它只能用静态/动态切换
粗略近似低速下降。因此：

1. 普通三摩擦 CMA 即使找到良好的 position 预测，也可能只是 simulator-effective
   补偿参数；
2. `dynamic_friction`/`viscous_friction` 贴近零可能来自结构表达不足，不应直接解释为
   硬件运动阻力真的为零；
3. 人为抬高下界只能制造一个“内部最优”，不能解决模型缺少 Stribeck 速度尺度的问题；
4. 普通标准 DCMotor 结果仍需保留，作为最简基线和部署兼容配置，但必须与周期/Stribeck
   增强模型分开报告。

#### 验证方案与接受条件

先使用现有 constant-speed structural 数据做离线模型比较，不启动昂贵 Isaac CMA：

```text
M0: r_f = sign(v)*F_c + B*v
M1: r_f = sign(v)*[F_c+(F_s-F_c)*exp(-(abs(v)/v_s)^alpha)] + B*v
tau_passive = -r_f(v) + periodic(q)
```

比较时必须：

- 在相同位置 phase-bin 对齐正反方向，用半和提取共同位置周期项，用半差提取方向奇对称
  的速度阻力；
- 只用稳态段，排除加速、换向、明显反馈间隙和 2 rad/s；1 rad/s 只作诊断；
- 按速度、方向和整圈等权，不允许长轨迹或某个速度档支配；
- 用不同 rotation/速度档做 held-out，而不是只比较训练残差；
- 约束 `F_s >= F_c >= 0`、`v_s>0`、`alpha>0`、`B>=0`；
- 报告 bootstrap/leave-one-speed-out 下参数稳定性，并检查残差是否仍与 q、方向或温度相关。

只有当 M1 在 held-out 数据上稳定优于 M0，且 `F_s/F_c/v_s` 在不同圈次、方向和速度
留出中不发生数量级漂移，才接受“存在可辨识 Stribeck 区域”。如果 M1 只在训练数据
降低误差，或 `v_s/alpha/B` 高度相关，则只报告“负斜率与 Stribeck 相容”，不能把完整
Stribeck 参数写进正式 actuator。

若该假设通过验证，增强执行器应独立命名为 `PeriodicStribeckDCMotor`，概念上包含：

```text
controller applied effort
+ k=126 position-periodic passive torque
+ direction-dependent Stribeck/Coulomb/viscous passive torque
```

`A/phase` 与 `F_s/F_c/v_s/alpha/B` 必须保存为自定义执行器参数；它们不是标准
`DCMotorCfg` 字段。普通 DCMotor 三摩擦辨识仍单独运行，作为不含周期和连续
Stribeck 的对照基线。
