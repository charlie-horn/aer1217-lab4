"""
2021-02 -- Wenda Zhao, Miller Tang

This is the class for a steoro visual odometry designed 
for the course AER 1217H, Development of Autonomous UAS
https://carre.utoronto.ca/aer1217
"""
import numpy as np
import cv2 as cv
import sys
import random

STAGE_FIRST_FRAME = 0
STAGE_SECOND_FRAME = 1
STAGE_DEFAULT_FRAME = 2

np.random.rand(1217)

class StereoCamera:
    def __init__(self, baseline, focalLength, fx, fy, cu, cv):
        self.baseline = baseline
        self.f_len = focalLength
        self.fx = fx
        self.fy = fy
        self.cu = cu
        self.cv = cv

class VisualOdometry:
    def __init__(self, cam):
        self.frame_stage = 0
        self.cam = cam
        self.new_frame_left = None
        self.last_frame_left = None
        self.new_frame_right = None
        self.last_frame_right = None
        self.C = np.eye(3)                               # current rotation    (initiated to be eye matrix)
        self.r = np.zeros((3,1))                         # current translation (initiated to be zeros)
        self.kp_l_prev  = None                           # previous key points (left)
        self.des_l_prev = None                           # previous descriptor for key points (left)
        self.kp_r_prev  = None                           # previous key points (right)
        self.des_r_prev = None                           # previoud descriptor key points (right)
        self.detector = cv.xfeatures2d.SIFT_create()     # using sift for detection
        self.feature_color = (255, 191, 0)
        self.inlier_color = (32,165,218)

            
    def feature_detection(self, img):
        kp, des = self.detector.detectAndCompute(img, None)
        feature_image = cv.drawKeypoints(img,kp,None)
        return kp, des, feature_image

    def featureTracking(self, prev_kp, cur_kp, img, color=(0,255,0), alpha=0.5):
        img = cv.cvtColor(img, cv.COLOR_GRAY2BGR)
        cover = np.zeros_like(img)
        # Draw the feature tracking 
        for i, (new, old) in enumerate(zip(cur_kp, prev_kp)):
            a, b = new.ravel()
            c, d = old.ravel()  
            a,b,c,d = int(a), int(b), int(c), int(d)
            cover = cv.line(cover, (a,b), (c,d), color, 2)
            cover = cv.circle(cover, (a,b), 3, color, -1)
        frame = cv.addWeighted(cover, alpha, img, 0.75, 0)
        
        return frame
    
    def find_feature_correspondences(self, kp_l_prev, des_l_prev, kp_r_prev, des_r_prev, kp_l, des_l, kp_r, des_r):
        VERTICAL_PX_BUFFER = 1                                # buffer for the epipolor constraint in number of pixels
        FAR_THRESH = 7                                        # 7 pixels is approximately 55m away from the camera 
        CLOSE_THRESH = 65                                     # 65 pixels is approximately 4.2m away from the camera
        
        nfeatures = len(kp_l)
        bf = cv.BFMatcher(cv.NORM_L2, crossCheck=True)        # BFMatcher for SIFT or SURF features matching

        ## using the current left image as the anchor image
        match_l_r = bf.match(des_l, des_r)                    # current left to current right
        match_l_l_prev = bf.match(des_l, des_l_prev)          # cur left to prev. left
        match_l_r_prev = bf.match(des_l, des_r_prev)          # cur left to prev. right

        kp_query_idx_l_r = [mat.queryIdx for mat in match_l_r]
        kp_query_idx_l_l_prev = [mat.queryIdx for mat in match_l_l_prev]
        kp_query_idx_l_r_prev = [mat.queryIdx for mat in match_l_r_prev]

        kp_train_idx_l_r = [mat.trainIdx for mat in match_l_r]
        kp_train_idx_l_l_prev = [mat.trainIdx for mat in match_l_l_prev]
        kp_train_idx_l_r_prev = [mat.trainIdx for mat in match_l_r_prev]

        ## loop through all the matched features to find common features
        features_coor = np.zeros((1,8))
        for pt_idx in np.arange(nfeatures):
            if (pt_idx in set(kp_query_idx_l_r)) and (pt_idx in set(kp_query_idx_l_l_prev)) and (pt_idx in set(kp_query_idx_l_r_prev)):
                temp_feature = np.zeros((1,8))
                temp_feature[:, 0:2] = kp_l_prev[kp_train_idx_l_l_prev[kp_query_idx_l_l_prev.index(pt_idx)]].pt 
                temp_feature[:, 2:4] = kp_r_prev[kp_train_idx_l_r_prev[kp_query_idx_l_r_prev.index(pt_idx)]].pt 
                temp_feature[:, 4:6] = kp_l[pt_idx].pt 
                temp_feature[:, 6:8] = kp_r[kp_train_idx_l_r[kp_query_idx_l_r.index(pt_idx)]].pt 
                features_coor = np.vstack((features_coor, temp_feature))
        features_coor = np.delete(features_coor, (0), axis=0)

        ##  additional filter to refine the feature coorespondences
        # 1. drop those features do NOT follow the epipolar constraint
        features_coor = features_coor[
                    (np.absolute(features_coor[:,1] - features_coor[:,3]) < VERTICAL_PX_BUFFER) &
                    (np.absolute(features_coor[:,5] - features_coor[:,7]) < VERTICAL_PX_BUFFER)]

        # 2. drop those features that are either too close or too far from the cameras
        features_coor = features_coor[
                    (np.absolute(features_coor[:,0] - features_coor[:,2]) > FAR_THRESH) & 
                    (np.absolute(features_coor[:,0] - features_coor[:,2]) < CLOSE_THRESH)]

        features_coor = features_coor[
                    (np.absolute(features_coor[:,4] - features_coor[:,6]) > FAR_THRESH) & 
                    (np.absolute(features_coor[:,4] - features_coor[:,6]) < CLOSE_THRESH)]

        # features_coor:
        # prev_l_x, prev_l_y, prev_r_x, prev_r_y, cur_l_x, cur_l_y, cur_r_x, cur_r_y
        return features_coor

    def inv_cam(self, f_l,f_r):
        #### convert feature points into 3D coordinate
        b = self.cam.baseline
        fu = self.cam.fx
        fv = self.cam.fy
        cu = self.cam.cu
        cv = self.cam.cv

        ul, vl = f_l[:,0], f_l[:, 1]
        ur, vr = f_r[:,0], f_r[:, 1]
        n = ur .shape[0]
        point = np.transpose(b/(ul-ur)*np.vstack([0.5*(ul+ur)-cu, fu/fv*(0.5*(vl+vr))-cv, np.full((1,n),fu)]))

        return point

    def ransac(self, features_coor):
        #return feature_coor
        num_features, _ = features_coor.shape
        inlier_threshold = 1
        min_inlier_fraction = 0.8
        min_inliers = min_inlier_fraction*num_features
        M = 3
        iterations = 100
        best_C = np.zeros((3,3))
        best_r = np.zeros((3,1))
        most_inliers = 0

        f_r_prev, f_r_cur = features_coor[:,2:4], features_coor[:,6:8]
        f_l_prev, f_l_cur = features_coor[:, 0:2], features_coor[:, 4:6]

        p_prev = self.inv_cam(f_l_prev,f_r_prev)
        p_cur = self.inv_cam(f_l_cur, f_r_cur)

        for i in range(iterations):
            chosen_features_ids = np.transpose(np.array(random.sample(range(num_features), M)))
            chosen_features = features_coor[chosen_features_ids,:]

            # Find "Model" for movement from a to b
            
            f_r_prev, f_r_cur = chosen_features[:,2:4], chosen_features[:,6:8]
            f_l_prev, f_l_cur = chosen_features[:, 0:2], chosen_features[:, 4:6]

            p_prev = self.inv_cam(f_l_prev,f_r_prev)
            p_cur = self.inv_cam(f_l_cur, f_r_cur)

            C_ba, r_ba_a = self.compute_T(p_prev, p_cur)  #change to inlier_previous and inlier_current only after integrating RANSAC
            r_ab_b = -np.dot(C_ba,r_ba_a)

            #check = np.transpose(p_cur) - np.add(np.matmul(C_ba,np.transpose(p_prev)), r_ab_b.reshape((3,1)))

            # Find inliers/outliers

            f_r_prev, f_r_cur = features_coor[:,2:4], features_coor[:,6:8]
            f_l_prev, f_l_cur = features_coor[:, 0:2], features_coor[:, 4:6]

            p_prev = self.inv_cam(f_l_prev,f_r_prev)
            p_cur = self.inv_cam(f_l_cur, f_r_cur)

            distances = np.sum(np.abs(np.transpose(p_cur) - np.add(np.matmul(C_ba,np.transpose(p_prev)), r_ab_b.reshape((3,1)))), axis=0)
            inlier_ids = np.where(distances<inlier_threshold)
            num_inliers = inlier_ids[0].shape[0]

            # Save best model

            if num_inliers > min_inliers:
                most_inliers = num_inliers
                best_inlier_ids = inlier_ids
                best_C = C_ba
                best_r = r_ab_b
                break
            elif num_inliers > most_inliers:
                most_inliers = num_inliers
                best_inlier_ids = inlier_ids
                best_C = C_ba
                best_r = r_ab_b
            
        #print("Ransac took ", i, "iterations, ", most_inliers, "inliers")
        features_coor = features_coor[best_inlier_ids]
        return features_coor

    def compute_T(self, points_a, points_b):
        # step 5
        num_p = len(points_a)
        p_a = np.average(points_a, axis=0)
        p_b = np.average(points_b, axis=0)
        w_ab = np.dot(np.transpose(points_b-p_b),(points_a - p_a)) / num_p

        # step 6
        v, s, u_T = np.linalg.svd(w_ab)
        u = np.transpose(u_T)
        det_u = np.linalg.det(u)
        det_v = np.linalg.det(v)

        # step 7
        temp = np.eye(3)
        temp[2,2] = det_u * det_v
        c_ba = np.dot(np.dot(v, temp),u_T)
        r_ba_a = -np.dot(np.transpose(c_ba),p_b) + p_a

        return c_ba, r_ba_a


    def pose_estimation(self, features_coor):
        # dummy C and r
        #C = np.eye(3)
        #r = np.array([0,0,0])
        # feature in right and left img (without filtering)
        
        # ------------- start your code here -------------- #
        # step 1 - 4
        features_coor = self.ransac(features_coor)
        f_r_prev, f_r_cur = features_coor[:,2:4], features_coor[:,6:8]
        f_l_prev, f_l_cur = features_coor[:, 0:2], features_coor[:, 4:6]
        
        p_prev = self.inv_cam(f_l_prev,f_r_prev)
        p_cur = self.inv_cam(f_l_cur, f_r_cur)

        # step 5 - 7
        C_ba, r_ba_a = self.compute_T(p_prev, p_cur)  #change to inlier_previous and inlier_current only after integrating RANSAC

        # step 8
        r_ab_b = -np.dot(C_ba,r_ba_a)
        
        # replace (1) the dummy C and r to the estimated C and r. 
        #         (2) the original features to the filtered features

        return C_ba, r_ab_b, f_r_prev, f_r_cur
    
    def processFirstFrame(self, img_left, img_right):
        kp_l, des_l, feature_l_img = self.feature_detection(img_left)
        kp_r, des_r, feature_r_img = self.feature_detection(img_right)
        
        self.kp_l_prev = kp_l
        self.des_l_prev = des_l
        self.kp_r_prev = kp_r
        self.des_r_prev = des_r
        
        self.frame_stage = STAGE_SECOND_FRAME
        return img_left, img_right
    
    def processSecondFrame(self, img_left, img_right):
        kp_l, des_l, feature_l_img = self.feature_detection(img_left)
        kp_r, des_r, feature_r_img = self.feature_detection(img_right)
    
        # compute feature correspondance
        features_coor = self.find_feature_correspondences(self.kp_l_prev, self.des_l_prev,
                                                     self.kp_r_prev, self.des_r_prev,
                                                     kp_l, des_l, kp_r, des_r)
        # draw the feature tracking on the left img
        img_l_tracking = self.featureTracking(features_coor[:,0:2], features_coor[:,4:6],img_left, color = self.feature_color)
        
        # lab4 assignment: compute the vehicle pose  
        [self.C, self.r, f_r_prev, f_r_cur] = self.pose_estimation(features_coor)
        
        # draw the feature (inliers) tracking on the right img
        img_r_tracking = self.featureTracking(f_r_prev, f_r_cur, img_right, color = self.inlier_color, alpha=1.0)
        
        # update the key point features on both images
        self.kp_l_prev = kp_l
        self.des_l_prev = des_l
        self.kp_r_prev = kp_r
        self.des_r_prev = des_r
        self.frame_stage = STAGE_DEFAULT_FRAME
        
        return img_l_tracking, img_r_tracking

    def processFrame(self, img_left, img_right, frame_id):
        kp_l, des_l, feature_l_img = self.feature_detection(img_left)

        kp_r, des_r, feature_r_img = self.feature_detection(img_right)
        
        # compute feature correspondance
        features_coor = self.find_feature_correspondences(self.kp_l_prev, self.des_l_prev,
                                                     self.kp_r_prev, self.des_r_prev,
                                                     kp_l, des_l, kp_r, des_r)
        # draw the feature tracking on the left img
        img_l_tracking = self.featureTracking(features_coor[:,0:2], features_coor[:,4:6], img_left,  color = self.feature_color)
        
        # lab4 assignment: compute the vehicle pose  
        [self.C, self.r, f_r_prev, f_r_cur] = self.pose_estimation(features_coor)
        
        # draw the feature (inliers) tracking on the right img
        img_r_tracking = self.featureTracking(f_r_prev, f_r_cur, img_right,  color = self.inlier_color, alpha=1.0)
        
        # update the key point features on both images
        self.kp_l_prev = kp_l
        self.des_l_prev = des_l
        self.kp_r_prev = kp_r
        self.des_r_prev = des_r

        return img_l_tracking, img_r_tracking
    
    def update(self, img_left, img_right, frame_id):
               
        self.new_frame_left = img_left
        self.new_frame_right = img_right
        
        if(self.frame_stage == STAGE_DEFAULT_FRAME):
            frame_left, frame_right = self.processFrame(img_left, img_right, frame_id)
            
        elif(self.frame_stage == STAGE_SECOND_FRAME):
            frame_left, frame_right = self.processSecondFrame(img_left, img_right)
            
        elif(self.frame_stage == STAGE_FIRST_FRAME):
            frame_left, frame_right = self.processFirstFrame(img_left, img_right)
            
        self.last_frame_left = self.new_frame_left
        self.last_frame_right= self.new_frame_right
        
        return frame_left, frame_right 


