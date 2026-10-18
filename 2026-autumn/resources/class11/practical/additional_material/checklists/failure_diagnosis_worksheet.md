# Failure diagnosis worksheet (Class 11, student activity, 10 minutes)

Supplied failure: episode 0 of `additional_material/data/videos/class11_rollout_pusher_ep000.mp4`, policy ACT trained on
300 simulated handheld Push Cube demonstrations (60k steps), executed on the simulated arm with the tool, chunk n = 100.
Result entry: success = false, 450 steps (time limit), final distance 3.1 cm.

1. What did the policy see at the moment the motion stopped making progress? (phone image: cube position, goal
   visible or not, rod position)  ______________________________________________

2. Which step (approximately) did the cube stop moving towards the goal? ______  What did the arm do afterwards?

3. Which rung of the evidence ladder does this result belong to? 1 / 2 / 3 / 4 / 5
   What does it show, and what does it not show about the physical arm? (two sentences)

4. Name one candidate cause from each group, and how you would tell them apart:
   data (visibility, demonstrations near the goal): ______________________
   policy / execution (chunk length, averaging of modes): ______________________
   dynamics (push distance per step, friction): ______________________

5. Next experiment: change exactly one factor. Factor: ______  Expected effect on the 50-episode success rate: ______
   What result would make you reject your hypothesis? ______

6. Which held-out condition would you test first before any hardware run, and why? ______
