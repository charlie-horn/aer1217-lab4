## Run the code: python lab4.py

## Output:
  - trajectory.png
  - video.avi

## RANSAC: 
  - stereo_vo_base.py line 133, ransac() takes in features in pixel coordinates and returns inliers in pixel coordinates
  
## Pose estimation
  - stereo_vo_base.py line 220, pose_estimation() takes in features in pixel coordinates, calls ransac, and returns the transformation matrix for the current frame
