# Class06 figure reproduction

From resources/class06,prepare a separate authoring environment with code/requirements-demo.txt and media/source/requirements-media.txt. Provide locally licensed MiSans Regular/Semibold files; no font binaries are bundled. Then run:

```sh
python media/source/generate_class06_figures.py --font /path/to/MiSans-Regular.ttf --font /path/to/MiSans-Semibold.ttf
```

This recreates eight paper/classroom figure sets in local media/figures/ from the included media/data/ and code/results/. Student media exports live in ../../media/class06,with -paper/-classroom filename suffixes. Copy the generated outputs there when publishing. Do not overwrite archived evidence without retaining its prior version.

The source render_class06_media.py reruns the selected episode to regenerate frames/animation and needs native graphics support plus fonts. The included animation/frames are retained prior renders. This release reran numerical seed9204playback and checked the complete error/event trace; it did not render new graphics. The six letterPNGtextures are generated artwork used without local font installation. The source generate_cube_artwork.py records their construction.

All diagrams are conceptual except plots of retained evaluation/trace data and the native storyboard. The eight generator functions are full_orientation,contact_wrench,feedback_loop,policy_and_clock,demo_storyboard,continuous_trace,qualification_results,paired_noise. No plot command trains a policy. Keep the model/policy licences and notices.
