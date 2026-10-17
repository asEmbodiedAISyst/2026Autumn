# RS06 跨数据集摩擦辨识

本文记录 2026-08-16 起采用的“重力释放先验 + 对称台架主动轨迹精调”流程。它替代
`friction=dynamic_friction` 的旧二维假设，但不删除旧结果；旧结果仍可用于说明为何
不能让一个 Coulomb 数同时承担起动保持和运动阻力。

## 1. 数据分别约束什么

三类数据不能简单拼成一个 sample-level loss：

- `manual_gravity_drop-2`：单侧负载、上电、Kp=Kd=0。已知重力矩提供绝对动力学
  激励，主要约束起动阈值、运动阻力和振荡包络。它给出当前局部先验
  `friction=0.238999 N·m`、`dynamic_friction=0.100366 N·m`、
  `viscous_friction=0.0445942 N·m/(rad/s)`。
- `hand-rotate`：上电、Kp=Kd=0、零前馈，人工逐个稳定小步移动。检测到 58 个
  稳定平台，典型输出轴步距为 `0.049869536 rad`，对应
  `k=125.99246`。电机 28 极等于 14 极对，乘 9:1 减速比恰为每输出轴圈
  `k=126`。该数据可靠约束周期和相位先验；因为手施力未知，不能辨识齿槽转矩幅值。
- R01–R13 对称台架主动轨迹：R01–R11 只用于 fit，R12/R13 在最优参数冻结后才
  validation。它们约束闭环位置跟踪下的 simulator-effective 摩擦；不得把它们
  与重力记录按样本数直接混合。

手转数据中的 q_target 固定、实测 q 被外力移动，因此绝不能作为普通位置命令回放。
其 torque 也是驱动器电流折算反馈，且不包含手施加转矩，不能用来标定 detent 幅值。

## 2. 当前模型与选择理由

主动台架使用本机 Isaac Lab 2.3.2 的 `DCMotorCfg`：

```python
DCMotorCfg(
    stiffness=50.0,
    damping=3.38,
    armature=1.2484886e-3,
    friction=F_static,
    dynamic_friction=F_dynamic,
    viscous_friction=B,
    effort_limit=36.0,
    saturation_effort=72.0,
    velocity_limit=53.0,
)
```

本阶段固定 armature、Kp 和 Kd，只优化
`[friction, dynamic_friction/friction, viscous_friction]` 的 log 坐标：

- `friction ∈ [0.12, 0.50] N·m`；
- `dynamic/static ∈ [0.20, 0.80]`，因此始终有
  `0 < dynamic_friction < friction`；
- `viscous_friction ∈ [0.015, 0.15] N·m/(rad/s)`。

初值和局部范围来自重力释放的保守固定-armature 解。配置文件
`rs06_friction_prior.yaml` 保存 prior 文件路径和 SHA-256；加载配置时会真实校验，
不一致时拒绝运行。主动轨迹没有加入显式 detent 转矩：现有手转数据只足以证明
`k=126`，重力数据对幅值 A 的 profile 又近乎平坦。把一个不可辨识的 A 放进主动
CMA 只会增加参数相关性。若以后取得带已知外力矩的准静态脱离数据，再单独扩展
自定义执行器；`A/phase/k` 不是 `DCMotorCfg` 字段。

目标函数使用归一化 Huber loss，q/v/torque 权重为 `1.0/0.03/0.005`。实机速度
反馈抖动明显，torque 虽已确认是 9:1 后的输出关节侧 N·m，但仍是电流折算值，
其效率、比例和滤波未知，所以两者只提供弱约束。每条轨迹内部先平均，R01–R11
再等权平均。

## 3. 运行与进度

正式入口：

```bash
../isaacsim/bin/python rs06_tool.py identify-friction-prior \
  --config rs06_friction_prior.yaml --seed 20260813 --num-envs 20 \
  --output-dir outputs/rs06_friction_prior_active_run01 \
  --wandb-mode online --wandb-project rs06-system-identification \
  --wandb-run-name rs06-friction-prior-active-run01 \
  --wandb-tag gravity-informed-friction --headless
```

预算为 2 个独立 restart、population 20、每个最多 30 代。并行一致性检查先比较
1 环境与 8 环境结果；只有 q/v/torque/loss 全部通过才使用 20 环境。每代写
checkpoint、CSV、`progress.json` 和 W&B。

正式运行已完成；运行期间可用以下命令查看，完成后以 JSON 工件为准：

```bash
systemctl --user status rs06-friction-prior-active-run01.service
tail -f logs/rs06_friction_prior_active_run01.log
watch -n 2 cat outputs/rs06_friction_prior_active_run01/progress.json
cat outputs/rs06_friction_prior_active_run01/wandb_run.json
```

异常中断后的恢复命令：

```bash
../isaacsim/bin/python rs06_tool.py identify-friction-prior \
  --config rs06_friction_prior.yaml --seed 20260813 --num-envs 20 \
  --resume outputs/rs06_friction_prior_active_run01 --headless
```

恢复时配置、版本、资产、数据、prior、seed 或裁剪语义不同都会被拒绝。

运行于 2026-08-16 20:59（Asia/Dubai）启动；单环境与 8 环境一致性检查的 q、v、
torque 和 loss 最大差异均为 0，正式评估使用 20 环境。在线进度为
`https://wandb.ai/changshan/rs06-system-identification/runs/x0ujwsy4`。首代实测
约 50 s，CMA 阶段约 0.83 h。最终 `workflow_status.json` 为 `complete`；数值以
同目录的 `effect_summary.json`、`model_interpretation.json` 和
`identifiability.json` 为准。

该运行经历两次整机异常关机。第一次在 restart 2 第 10 代后恢复，第二次发生在
60 代 CMA、冻结 evaluation 和图表均保存之后，只需恢复 identifiability。两个
checkpoint 均通过 signature 校验，W&B 继续使用同一 run id；没有把中断前后的
候选误当作独立 restart。

## 4. 判断优化是否真的有效

不要只看 CMA 的最低数字。完成后按以下顺序判断：

1. `effect_summary.json`：best 是否明显优于重力 prior 初值；R12/R13 冻结
   validation 是否同方向改善。
2. `optimization_summary.json`：两个 restart 是否得到接近的 loss 和参数；任何
   `boundary_hits` 都代表跨数据集冲突或模型不足，不能自动扩界。
3. `best/trajectory_metrics.csv` 与逐轨迹图：R01/R02/R04 的停顿与换向、
   R03/R05/R06 的较大运动、R07–R11 的动态是否由同一参数组共同改善。
4. `identifiability.json`：单参数 profile、log Hessian 条件数、参数相关性和 Kp/Kd
   ±5%/±10% 敏感性。参数减半或翻倍而 fit loss 变化不超过 1% 时必须标为弱可辨识。

2026-08-16 的冻结基线检查把重力 prior 四字段直接用于主动轨迹，得到 fit
`15.2811`、validation `26.0135`。与旧的 position-primary、绑定动静摩擦网格
最优 `14.3614/23.3532` 相比仅差约 6.4%/11.4%，说明重力先验并未与主动数据
严重矛盾；但旧网格把两类 Coulomb 摩擦绑在一起，且同时滑向最低边界，物理解释
不成立。当前三摩擦局部 CMA 用于判断分离后能否保留较大的起动摩擦，同时改善
主动跟踪。

## 5. 现有数据的能力边界

当前数据足够选出一个可复现的、用于 Isaac 400 Hz 显式位置控制器的主动台架
平滑 DCMotorCfg 搜索域最优值，并能检验该模型能否跨重力与主动数据解释；但三项
摩擦的 profile 均属于弱可辨识，不能称为唯一物理常数。以下量也不足以高置信度
唯一辨识：

- detent 幅值 A：缺少已知手力/外力矩；
- 断电机械摩擦与上电保持摩擦的分离：尚无断电自由摆；
- armature：重力联合搜索命中 `8e-3` 上界，说明它在吸收未建模动态，因此本阶段
  固定为减速比折算先验；
- 硬件内部速度滤波、torque 电流换算效率和 >1 kHz 控制器动态。

如果两个 restart 分歧大、参数 profile 平坦，或 validation 明显恶化，结论应是
“当前平滑 DCMotorCfg 摩擦模型对这些数据仍不足/参数弱可辨识”，而不是继续扩大
边界直到得到一组看似精确的数。

## 6. 主动平滑摩擦正式结果

`outputs/rs06_friction_prior_active_run01` 的两次 restart、共 60 代和 1200 个候选
得到：

- armature 固定 `1.2484886e-3 kg·m²`；
- `friction=0.1261617594 N·m`；
- `dynamic_friction=0.02526096092 N·m`；
- `viscous_friction=0.01500425533 N·m/(rad/s)`；
- R01–R11 fit `14.5442647`，相对重力 prior 初值的 `15.2811260` 改善 4.82%；
- 参数冻结后 R12/R13 validation 等轨迹均值 `23.8680703`。

第二个 restart 得到 fit `14.5443707`，与第一名仅差约 0.00073%，说明数值盆地可
复现。它同时给出 static `0.1200359`、dynamic/static 几乎 0.2、viscous 几乎
0.015。正式全局解的 dynamic/static ratio 和 viscous 已在 1% 归一化容差内命中
局部重力先验下界。因此这些值是“当前约束域内的主动台架平滑摩擦最优”，不是
三项均已物理唯一辨识；不得继续向下扩界并把更低 loss 当成更真实。

逐轨迹 position RMSE 最好的是 R09 `0.00569 rad`，最差的 fit 是 R06
`0.03144 rad`，其次 R11 `0.02314 rad`、R05 `0.02150 rad`。validation 的 R12/R13
分别为 `0.01344/0.02662 rad`。这表明主要剩余误差集中在加速、随机宽频和较大运动，
而非小幅/低速位置本身。

## 7. Armature 专项证据

新增根目录入口 `armature-profile`。它固定上面的主动摩擦数值，在完整
`[2.5e-4,8e-3] kg·m²`（32 倍范围）评估 25 个 log 点，并同时报告：

- R01–R11 等轨迹 loss；
- R06/R07/R08 加速与扫频子集；
- R03/R06/R07/R08/R11 动态激励子集；
- 每条轨迹 position/velocity/torque Huber；
- fit 选出的点冻结后的 R12/R13 validation。

配置 `rs06_armature_profile.yaml` 对当前摩擦参数文件做 SHA-256 校验。运行命令：

```bash
../isaacsim/bin/python rs06_tool.py armature-profile \
  --config rs06_armature_profile.yaml --profile-points 25 --num-envs 25 \
  --output-dir outputs/rs06_active_armature_profile_run01 \
  --wandb-mode online --wandb-project rs06-system-identification \
  --wandb-run-name rs06-active-armature-profile-run01 \
  --wandb-tag armature-identifiability --headless
```

该结果明确标为 fixed-nuisance slice：如果 32 倍参数变化导致 loss 变化不超过 1%，
或最小值在边界，它足以否定当前数据对 armature 的可辨识性；即使出现内部最小值，
也不能单独证明可辨识，因为 friction、viscous 和 Kd 尚未逐点重优化。此时还要与
既有四参数 joint CMA 和重力条件 profile 交叉检查。

正式结果位于 `outputs/rs06_active_armature_profile_run01`，单环境/并行结果逐项完全
一致。R01–R11 的 25 点曲线从 `2.5e-4` 到 `8e-3 kg·m²` 单调上升，最小值落在
下界：

- 下界 fit 为 `14.4994315`，上界为 `14.8915281`，32 倍全范围只变化 2.704%；
- 固定物理先验 `1.2484886e-3` 的精确 fit 为 `14.5442647`，相对下界只高
  `0.3092%`，低于本工程的 1% 弱可辨识阈值；
- R06/R07/R08 子集和 R03/R06/R07/R08/R11 动态子集也都严格偏好下界，全范围
  分别只变化 2.350% 和 3.058%；
- 先验解 validation 为 `23.8680703`，下界解为 `23.7712350`，只改善 0.407%，
  validation 未参与选点。

自由落体不能把这一趋势变成有限估计。上电、Kp=Kd=0 的单侧重力最终六参数联合
CMA 的两个 restart 分别得到 armature `0.00798029` 和 `0.00799981 kg·m²`，均命中
相反的上界。此前每点仅 8 代/80 候选的条件 profile 曾在 `0.00380678` 出现内部
最小值，但更完整联合拟合的 loss 又低 26.963%，所以该内部点是 nuisance 搜索不足
造成的不稳定证据。主动下界与重力上界没有共同有限最优，证明当前模型在吸收上电
保持、周期阻力、摩擦或控制器动态，而不是识别同一个 rotor inertia。

此外，物理先验只占 CAD 负载轴向惯量 `0.057679035 kg·m²` 的 2.165%；Kp/Kd
±10% 诊断最多可改善主动 loss 25.72%，远大于先验到 armature 下界的 0.309%。因此
当前推荐仍是固定 `armature=1.2484886e-3`，并明确标记为 9:1 折算物理先验，不是
数据拟合值。机器可读的跨数据集证据、源文件 SHA-256 和图由以下无仿真命令生成：

```bash
../isaacsim/bin/python scripts/summarize_rs06_evidence.py
```

输出为 `outputs/rs06_armature_evidence_run01/armature_evidence.json`、
`armature_evidence.png` 和 `README.md`。若要释放 armature，至少需要断使能但编码器
可读的多初角/双方向释放，或第二个已知且明显更低的惯量配置；当前上电自由落体仅能
辅助约束，不足以独立辨识。

## 8. 周期阻力幅值需要的新数据

`hand-rotate` 已确定 `k=126`，但未知手力不能确定幅值。首选采集上电 Kp=Kd=0
条件下、带已知力臂和同步拉力计的双向脱离阈值地图。对同一 q 的带符号正负脱离
力矩 `T+`、`T-`：

```text
tau_periodic(q) ≈ -(T+(q) + T-(q)) / 2
F_static(q)     ≈  (T+(q) - T-(q)) / 2
```

至少覆盖一整圈、每个方向三遍，并保留 raw encoder count；实验之间不要重新标零。
建议同时采集断电对照。若没有外部力传感器，次优方案是在相同已知 Kp/Kd 下做
`±0.05/±0.10/±0.20 rad/s` 的正反整圈恒速扫描，每档每向至少三圈。50 Hz 下
0.10 rad/s 可为每个 2.86° 周期提供约 25 帧；按角度配对后的正反 torque 半和
主要保留周期项、半差主要保留 Coulomb/viscous，但幅值仍受电流换算和驱动滤波影响。
