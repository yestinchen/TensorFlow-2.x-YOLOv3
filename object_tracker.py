#================================================================
#
#   File name   : object_tracker.py
#   Author      : PyLessons
#   Created date: 2020-07-27
#   Website     : https://pylessons.com/
#   GitHub      : https://github.com/pythonlessons/TensorFlow-2.x-YOLOv3
#   Description : code to track detected object from video or webcam
#
#================================================================
import os
os.environ['CUDA_VISIBLE_DEVICES'] = '1'
import cv2
import numpy as np
import tensorflow as tf
from yolov3.yolov3 import Create_Yolov3
from yolov3.yolov4 import Create_Yolo
from yolov3.utils import load_yolo_weights, image_preprocess, postprocess_boxes, nms, draw_bbox, read_class_names#, detect_image, detect_video, detect_realtime
import time
from yolov3.configs import *

from deep_sort import nn_matching
from deep_sort.detection import Detection
from deep_sort.tracker import Tracker
from deep_sort import generate_detections as gdet

if YOLO_TYPE == "yolov4":
    Darknet_weights = YOLO_V4_TINY_WEIGHTS if TRAIN_YOLO_TINY else YOLO_V4_WEIGHTS
if YOLO_TYPE == "yolov3":
    Darknet_weights = YOLO_V3_TINY_WEIGHTS if TRAIN_YOLO_TINY else YOLO_V3_WEIGHTS

# video_path   = "./IMAGES/test.mp4"
# video_path = '/media/ytchen/hdd/dataset/youtube/traffic1.mp4'

yolo = Create_Yolo(input_size=YOLO_INPUT_SIZE)
load_yolo_weights(yolo, Darknet_weights) # use Darknet weights
def Object_tracking(YoloV3, video_path, output_path, input_size=416, show=False, CLASSES=YOLO_COCO_CLASSES, 
  score_threshold=0.3, iou_threshold=0.45, rectangle_colors='', Track_only = [], output_txt_path=''):
    # Definition of the parameters
    max_cosine_distance = 0.7
    nn_budget = None
    
    #initialize deep sort object
    model_filename = 'model_data/mars-small128.pb'
    encoder = gdet.create_box_encoder(model_filename, batch_size=1)
    metric = nn_matching.NearestNeighborDistanceMetric("cosine", max_cosine_distance, nn_budget)
    tracker = Tracker(metric)

    times = []

    if video_path:
        vid = cv2.VideoCapture(video_path) # detect on video
    else:
        vid = cv2.VideoCapture(0) # detect from webcam

    # by default VideoCapture returns float instead of int
    width = int(vid.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(vid.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = int(vid.get(cv2.CAP_PROP_FPS))
    codec = cv2.VideoWriter_fourcc(*'XVID')
    out = cv2.VideoWriter(output_path, codec, fps, (width, height)) # output_path must be .mp4

    NUM_CLASS = read_class_names(CLASSES)
    key_list = list(NUM_CLASS.keys()) 
    val_list = list(NUM_CLASS.values())
    if output_txt_path != '':
      output_file = open(output_txt_path, 'w')
    idx = 0
    start = time.time()
    while True:
        _, img = vid.read()
        idx += 1

        try:
            original_image = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            original_image = cv2.cvtColor(original_image, cv2.COLOR_BGR2RGB)
        except:
            break
        image_data = image_preprocess(np.copy(original_image), [input_size, input_size])
        image_data = tf.expand_dims(image_data, 0)
        
        t1 = time.time()
        pred_bbox = YoloV3.predict(image_data)
        t2 = time.time()

        times.append(t2-t1)
        times = times[-20:]
        
        pred_bbox = [tf.reshape(x, (-1, tf.shape(x)[-1])) for x in pred_bbox]
        pred_bbox = tf.concat(pred_bbox, axis=0)

        bboxes = postprocess_boxes(pred_bbox, original_image, input_size, score_threshold)
        bboxes = nms(bboxes, iou_threshold, method='nms')

        # extract bboxes to boxes (x, y, width, height), scores and names
        boxes, scores, names = [], [], []
        for bbox in bboxes:
            if len(Track_only) !=0 and NUM_CLASS[int(bbox[5])] in Track_only or len(Track_only) == 0:
                boxes.append([bbox[0].astype(int), bbox[1].astype(int), bbox[2].astype(int)-bbox[0].astype(int), bbox[3].astype(int)-bbox[1].astype(int)])
                scores.append(bbox[4])
                names.append(NUM_CLASS[int(bbox[5])])

        # Obtain all the detections for the given frame.
        boxes = np.array(boxes) 
        names = np.array(names)
        scores = np.array(scores)
        features = np.array(encoder(original_image, boxes))
        detections = [Detection(bbox, score, class_name, feature) for bbox, score, class_name, feature in zip(boxes, scores, names, features)]

        # Pass detections to the deepsort object and obtain the track information.
        tracker.predict()
        tracker.update(detections)

        # Obtain info from the tracks
        tracked_bboxes = []
        for track in tracker.tracks:
            if not track.is_confirmed() or track.time_since_update > 5:
                continue 
            bbox = track.to_tlbr() # Get the corrected/predicted bounding box
            class_name = track.get_class() #Get the class name of particular object
            tracking_id = track.track_id # Get the ID for the particular track
            index = key_list[val_list.index(class_name)] # Get predicted object index by object name
            tracked_bboxes.append(bbox.tolist() + [tracking_id, index]) # Structure data, that we could use it with our draw_bbox function

        ms = sum(times)/len(times)*1000
        fps = 1000 / ms

        # draw detection on frame
        image = draw_bbox(original_image, tracked_bboxes, CLASSES=CLASSES, tracking=True)
        image = cv2.putText(image, "Time: {:.1f} FPS".format(fps), (0, 30), cv2.FONT_HERSHEY_COMPLEX_SMALL, 1, (0, 0, 255), 2)

        # draw original yolo detection
        #image = draw_bbox(image, bboxes, CLASSES=CLASSES, show_label=False, rectangle_colors=rectangle_colors, tracking=True)

        #print("Time: {:.2f}ms, {:.1f} FPS".format(ms, fps))
        if output_path != '': out.write(image)
        if output_file != None: 
          for tbb in tracked_bboxes:
            output_file.write('{}: {}\n'.format(idx, tbb))

        if show:
            cv2.imshow('output', image)
            
            if cv2.waitKey(25) & 0xFF == ord("q"):
                cv2.destroyAllWindows()
                break
            
    cv2.destroyAllWindows()
    end = time.time()
    print("total time: {}s".format(end - start))
    if output_file != None:
      output_file.write('#TIME:{}'.format(end-start))
      output_file.close()


# video_path = '/media/ytchen/hdd/working/yolo/MVI_40751/MVI_40751.mp4'
# out_video_path='/media/ytchen/hdd/working/yolo/MVI_40751/tracked.mp4'
# out_txt_path='/media/ytchen/hdd/working/yolo/MVI_40751/tracked.txt'

base_path = '/media/ytchen/hdd/working/yolo-2/'
# tasks = ['news1']
# tasks = ['news2', 'news3']
# tasks = ['traffic2', 'traffic3']
# tasks = ['joker', 'inception', 'ff']
# tasks = ['midway']
# tasks = ['MVI_40171', 'MOT16-06', 'MOT16-13','traffic1']
# tasks=['MVI_40751']
tasks = ['visualroad1', 'visualroad2', 'visualroad3', 'visualroad4', 'MVI_40171', 'MOT16-06', 'MOT16-13','MVI_40751']
# tasks = ['MVI_40171', 'MOT16-06', 'MOT16-13','MVI_40751']

for task in tasks:
  print('start working: {}'.format(task))
  video_path = "{}/{}/{}.mp4".format(base_path,task, task)
  out_video_path = "{}/{}/tracked-yolo-0.2.mp4".format(base_path, task)
  out_txt_path="{}/{}/tracked-yolo-0.2.txt".format(base_path, task)
  Object_tracking(yolo, video_path, out_video_path, input_size=YOLO_INPUT_SIZE, show=False, output_txt_path=out_txt_path,
  iou_threshold=0.1, score_threshold=0.2, rectangle_colors=(255,0,0), Track_only = ["person","car","truck","bus"])
