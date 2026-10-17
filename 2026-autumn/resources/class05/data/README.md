# Class 05 data contract

`episode_metrics.csv`: unchanged supplied metric rows for accepted calibration, selection and held-out motor records. `synthetic_baseline` and `hardware_fitted` are paired prediction methods; hardware_fitted is a simulator fitted to hardware records, not a second measured trajectory. Position RMSE uses the original active-profile scoring interval. Averaging per-record RMSE gives each record equal weight.

`EPISODES_USED.csv`: accepted simultaneous event list, with original private development-tree paths omitted. Each event contains16motor identities. Split by simultaneous event, not separate motor rows.

`fitted_parameters.csv`: unchanged selected effective parameters for16 motors×2controller contexts, plus shared baseline. Parameters are effective model values, not independently measured motor constants.

`paired-trace.csv`: lossless selected columns from the supplied two_motor_heldout_subset.parquet, event G1_16__H1__P06_heldout_composite__R01, motors0and9,2196rows. It contains recorded encoder position and stored simulated predictions. No resampling, smoothing or refitting. Motor0 has 1101 samples over0–11.000286455s; motor9 has 1095over0–10.990389566s. Direct RMSE over these supplied samples agrees with the corresponding published episode scores within5e-12 rad. Keep each motor’s time vector; row-index matching is not synchronization.

Loaded nominal fixture mass in this campaign's construction is113 g (25 g link+two4 g pins+two 40 g payloads). Distinguish98 g and110 g records elsewhere. Physical fixture correspondence remains unresolved.

The full original raw collection, video archive, optimizer reconstruction and neural training are outside this compact student package. Numerical reaggregation is reproducible here; it does not independently validate the original recording or modeling procedure.


## Baseline, candidates and interpretation

The single synthetic_baseline vector is shared across all motors and contexts. The32 hardware_fitted vectors are context/motor-specific effective parameters. Two numerical starts per cell produced64 source candidates; the source selects by model-selection error and freezes32 before held-out scoring. Two starts are not two hardware repetitions. The supplied selection record preserves this declaration; these commands do not independently reconstruct that optimizer procedure.

The accepted selection split is12 events underH1 and11 underH2. Do not substitute a balanced24event matrix from the separate Class 04 campaign.

The position/velocity references are separate device fields; velocity must not be silently replaced by a numerical derivative of the exported position reference. The selected compact CSV contains position reference and response/predictions only; it lacks the full reference/velocity/initial-state/configuration stream needed to reconstruct population replay. All current score calculations therefore use saved predictions.

The combined scenes are executable nominal 113gmechanical models with selected parameters. Compiling or stepping them does not reproduce the supplied hardware-data scoring run or resolve fixture identity.
