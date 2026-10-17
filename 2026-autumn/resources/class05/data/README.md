# Class05 data contract

`episode_metrics.csv`: unchanged supplied metric rows for accepted calibration, selection and held-out motor records. `synthetic_baseline` and `hardware_fitted` are paired prediction methods; hardware_fitted is a simulator fitted to hardware records, not a second measured trajectory. Position RMSE uses the original active-profile scoring interval. Averaging per-record RMSE gives each record equal weight.

`EPISODES_USED.csv`: accepted simultaneous event list, with original private development-tree paths omitted. Each event contains16motor identities. Split by simultaneous event, not separate motor rows.

`fitted_parameters.csv`: unchanged selected effective parameters for16motors×2controller contexts, plus shared baseline. Parameters are effective model values, not independently measured motor constants.

`paired-trace.csv`: lossless selected columns from the supplied two_motor_heldout_subset.parquet, event G1_16__H1__P06_heldout_composite__R01, motors0and9,2196rows. It contains recorded encoder position and stored simulated predictions. No resampling, smoothing or refitting. The plotted span is not a replacement definition of the original metric interval.

Loaded nominal fixture mass in this campaign's construction is113g (25g link+two4g pins+two40g payloads). Distinguish98g and110g records elsewhere. Physical fixture correspondence remains unresolved.

The full original raw collection, video archive, optimizer reconstruction and neural training are outside this compact student package. Numerical reaggregation is reproducible here; it does not independently validate the original recording or modeling procedure.
