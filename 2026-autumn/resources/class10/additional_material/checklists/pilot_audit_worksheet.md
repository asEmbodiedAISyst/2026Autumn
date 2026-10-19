# Pilot audit worksheet (Class 10, student activity, 10 minutes)

Run the audit script on the pilot dataset, open two or three episodes in the viewer if time allows, and give a verdict
for every episode BEFORE you open `audit_reference.json`.

    cd additional_material/rebot_pusher        # from the class folder; uv sync once
    uv run python ../code/audit_dataset.py ../data/pilot_push_cube_handheld

| Episode | Accept / reject | Reason (one line, with the number you used) |
| --- | --- | --- |
| 0 | | |
| 1 | | |
| 2 | | |
| 3 | | |
| 4 | | |
| 5 | | |
| 6 | | |
| 7 | | |
| 8 | | |
| 9 | | |

Then answer:

1. Which faults can the script detect from the parquet files alone, and which need the images or the robot model?
2. Which threshold did you use for "task completed"? Where does it come from?
3. Compare with `audit_reference.json`. Which of your verdicts changed, and why?
4. Fill the dataset contract template for this dataset (the clean part of it: the accepted episodes).
