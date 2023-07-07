from os import listdir, path
import numpy as np
import scipy
import cv2
import os, sys, argparse
import audio
import json, subprocess, random, string
from tqdm import tqdm
from glob import glob
import torch, face_detection
from models import Wav2Lip
import platform
import base64
import io
import uuid
from potassium import Potassium, Request, Response

app = Potassium("my_app")
print('This is APP.PY')
checkpoint_path = "./static/wav2lip.pth"


face = "./static/videoplayback.mp4"
audio_file = "./static/audio.wav"
# outfile='results/result_voice.mp4'
static = False
fps = 25
pads = [0, 10, 0, 0]
face_det_batch_size = 16
wav2lip_batch_size = 128
resize_factor = 1
crop = [0, -1, 0, -1]
box = [-1, -1, -1, -1]
rotate = False
nosmooth = False
img_size = 96
mel_step_size = 16
device = 'cuda' if torch.cuda.is_available() else 'cpu'
print("Using {} for inference.".format(device))

@app.init
def init():
    print('init started')
    print("#"*100)
    # global model
    model = load_model(checkpoint_path)
    print('init done')
    print("#"*100)
    context = {'model':model}
    return context


def get_smoothened_boxes(boxes, T):
    for i in range(len(boxes)):
        if i + T > len(boxes):
            window = boxes[len(boxes) - T :]
        else:
            window = boxes[i : i + T]
        boxes[i] = np.mean(window, axis=0)
    return boxes


def face_detect(images):
    detector = face_detection.FaceAlignment(
        face_detection.LandmarksType._2D, flip_input=False, device=device
    )

    batch_size = face_det_batch_size

    while 1:
        predictions = []
        try:
            for i in tqdm(range(0, len(images), batch_size)):
                predictions.extend(
                    detector.get_detections_for_batch(
                        np.array(images[i : i + batch_size])
                    )
                )
        except RuntimeError:
            if batch_size == 1:
                raise RuntimeError(
                    "Image too big to run face detection on GPU. Please use the --resize_factor argument"
                )
            batch_size //= 2
            print("Recovering from OOM error; New batch size: {}".format(batch_size))
            continue
        break

    results = []
    pady1, pady2, padx1, padx2 = pads
    for rect, image in zip(predictions, images):
        if rect is None:
            cv2.imwrite(
                "temp/faulty_frame.jpg", image
            )  # check this frame where the face was not detected.
            raise ValueError(
                "Face not detected! Ensure the video contains a face in all the frames."
            )

        y1 = max(0, rect[1] - pady1)
        y2 = min(image.shape[0], rect[3] + pady2)
        x1 = max(0, rect[0] - padx1)
        x2 = min(image.shape[1], rect[2] + padx2)

        results.append([x1, y1, x2, y2])

    boxes = np.array(results)
    if not nosmooth:
        boxes = get_smoothened_boxes(boxes, T=5)
    results = [
        [image[y1:y2, x1:x2], (y1, y2, x1, x2)]
        for image, (x1, y1, x2, y2) in zip(images, boxes)
    ]

    del detector
    return results


def datagen(frames, mels):
    img_batch, mel_batch, frame_batch, coords_batch = [], [], [], []

    if box[0] == -1:
        if not static:
            face_det_results = face_detect(frames)  # BGR2RGB for CNN face detection
        else:
            face_det_results = face_detect([frames[0]])
    else:
        print("Using the specified bounding box instead of face detection...")
        y1, y2, x1, x2 = box
        face_det_results = [[f[y1:y2, x1:x2], (y1, y2, x1, x2)] for f in frames]

    for i, m in enumerate(mels):
        idx = 0 if static else i % len(frames)
        frame_to_save = frames[idx].copy()
        face, coords = face_det_results[idx].copy()

        face = cv2.resize(face, (img_size, img_size))

        img_batch.append(face)
        mel_batch.append(m)
        frame_batch.append(frame_to_save)
        coords_batch.append(coords)

        if len(img_batch) >= wav2lip_batch_size:
            img_batch, mel_batch = np.asarray(img_batch), np.asarray(mel_batch)

            img_masked = img_batch.copy()
            img_masked[:, img_size // 2 :] = 0

            img_batch = np.concatenate((img_masked, img_batch), axis=3) / 255.0
            mel_batch = np.reshape(
                mel_batch, [len(mel_batch), mel_batch.shape[1], mel_batch.shape[2], 1]
            )

            yield img_batch, mel_batch, frame_batch, coords_batch
            img_batch, mel_batch, frame_batch, coords_batch = [], [], [], []

    if len(img_batch) > 0:
        img_batch, mel_batch = np.asarray(img_batch), np.asarray(mel_batch)

        img_masked = img_batch.copy()
        img_masked[:, img_size // 2 :] = 0

        img_batch = np.concatenate((img_masked, img_batch), axis=3) / 255.0
        mel_batch = np.reshape(
            mel_batch, [len(mel_batch), mel_batch.shape[1], mel_batch.shape[2], 1]
        )

        yield img_batch, mel_batch, frame_batch, coords_batch


def _load(checkpoint_path):
    if device == "cuda":
        checkpoint = torch.load(checkpoint_path)
    else:
        checkpoint = torch.load(
            checkpoint_path, map_location=lambda storage, loc: storage
        )
    return checkpoint


def load_model(path):
    model = Wav2Lip()
    print("Load checkpoint from: {}".format(path))
    checkpoint = _load(path)
    s = checkpoint["state_dict"]
    new_s = {}
    for k, v in s.items():
        new_s[k.replace("module.", "")] = v
    model.load_state_dict(new_s)

    model = model.to(device)
    return model.eval()


# HELPER FUNCTION FOR BASE64 ENCODING AND DECODING
def base64_to_file(base64_string, output_file):
    # Decode the Base64 string into binary data
    with open(output_file, 'wb') as f:
        try:
            f.write(base64.b64decode(base64_string))
        except Exception as e:
            print("Error writing file:", e)
    print(f"BASE64 ENCODED DATA SAVE TO {output_file}")
    print("-"*100)

def file_to_base64(file_path):
    with open(file_path, "rb") as f:
        base64_encoding =  base64.b64encode(f.read()).decode('utf-8')
    return base64_encoding

# def inference(all_inputs:dict)->dict:
@app.handler()
def handler(context:dict, request:Request)->Response:
    all_inputs = request.json
    # try:
    #     model_inputs = response.json.loads(request.json)
    # except:
    #     model_inputs = request.json
    # output = user_src.inference(model_inputs)
    # return response.json(output)
    
    # global model
    model = context.get('model')
    #VALIDATION ==================================================================
    if "audio" not in all_inputs or "video" not in all_inputs:
        return {'result':-1,'message':'audio/video absent in request',"all_inputs":all_inputs}
    
    audio_base64_encoding = all_inputs['audio']
    video_base64_encoding = all_inputs['video']
    #FILE PROCESSING ==================================================================
    file_id = str(uuid.uuid4())
    audio_filename = os.path.join("/tmp/uploads",file_id+".wav")
    video_filename = os.path.join("/tmp/uploads",file_id+".mp4")
    output_video_file = os.path.join("/tmp/results",file_id+".mp4")
    
    os.makedirs("/tmp/uploads",exist_ok=True)
    os.makedirs("/tmp/results",exist_ok=True)
    # try:
    # video file 
    base64_to_file(base64_string=audio_base64_encoding,output_file=audio_filename)
    base64_to_file(base64_string=video_base64_encoding,output_file=video_filename)
    # except:
    #     return {'result':-1,'message':'something went wrong during base64 decoding'}
    #==================================================================
    face = video_filename
    audio_file = audio_filename
    if not os.path.isfile(face):
        raise ValueError("--face argument must be a valid path to video/image file")

    elif face.split(".")[1] in ["jpg", "png", "jpeg"]:
        full_frames = [cv2.imread(face)]
        fps = fps

    else:
        video_stream = cv2.VideoCapture(face)
        fps = video_stream.get(cv2.CAP_PROP_FPS)

        print("Reading video frames...")

        full_frames = []
        while 1:
            still_reading, frame = video_stream.read()
            if not still_reading:
                video_stream.release()
                break
            if resize_factor > 1:
                frame = cv2.resize(
                    frame,
                    (frame.shape[1] // resize_factor, frame.shape[0] // resize_factor),
                )

            if rotate:
                frame = cv2.rotate(frame, cv2.cv2.ROTATE_90_CLOCKWISE)

            y1, y2, x1, x2 = crop
            if x2 == -1:
                x2 = frame.shape[1]
            if y2 == -1:
                y2 = frame.shape[0]

            frame = frame[y1:y2, x1:x2]

            full_frames.append(frame)

    print("Number of frames available for inference: " + str(len(full_frames)))

    if not audio_file.endswith(".wav"):
        print("Extracting raw audio...")
        command = "ffmpeg -y -i {} -strict -2 {}".format(audio_file, "temp/temp.wav")

        subprocess.call(command, shell=True)
        audio_file = "temp/temp.wav"

    wav = audio.load_wav(audio_file, 16000)
    mel = audio.melspectrogram(wav)
    print(mel.shape)

    if np.isnan(mel.reshape(-1)).sum() > 0:
        raise ValueError(
            "Mel contains nan! Using a TTS voice? Add a small epsilon noise to the wav file and try again"
        )

    mel_chunks = []
    mel_idx_multiplier = 80.0 / fps
    i = 0
    while 1:
        start_idx = int(i * mel_idx_multiplier)
        if start_idx + mel_step_size > len(mel[0]):
            mel_chunks.append(mel[:, len(mel[0]) - mel_step_size :])
            break
        mel_chunks.append(mel[:, start_idx : start_idx + mel_step_size])
        i += 1

    print("Length of mel chunks: {}".format(len(mel_chunks)))

    full_frames = full_frames[: len(mel_chunks)]

    batch_size = wav2lip_batch_size
    gen = datagen(full_frames.copy(), mel_chunks)

    for i, (img_batch, mel_batch, frames, coords) in enumerate(
        tqdm(gen, total=int(np.ceil(float(len(mel_chunks)) / batch_size)))
    ):
        if i == 0:
            

            frame_h, frame_w = full_frames[0].shape[:-1]
            out = cv2.VideoWriter(
                "temp/result.avi",
                cv2.VideoWriter_fourcc(*"DIVX"),
                fps,
                (frame_w, frame_h),
            )

        img_batch = torch.FloatTensor(np.transpose(img_batch, (0, 3, 1, 2))).to(device)
        mel_batch = torch.FloatTensor(np.transpose(mel_batch, (0, 3, 1, 2))).to(device)

        with torch.no_grad():
            pred = model(mel_batch, img_batch)

        pred = pred.cpu().numpy().transpose(0, 2, 3, 1) * 255.0

        for p, f, c in zip(pred, frames, coords):
            y1, y2, x1, x2 = c
            p = cv2.resize(p.astype(np.uint8), (x2 - x1, y2 - y1))

            f[y1:y2, x1:x2] = p
            out.write(f)

    out.release()
    # print("ERROR---------------------------------------------------- 1")
    command = "ffmpeg -y -i {} -i {} -strict -2 -q:v 1 {}".format(
        audio_filename, "temp/result.avi", output_video_file
    )
    subprocess.call(command, shell=platform.system() != "Windows")
    # print("ERROR---------------------------------------------------- 2")
    result_video_base64_encoding = file_to_base64(file_path=output_video_file)
    # return {
    #     "status":"success",
    #     "base64_encoding":result_video_base64_encoding
    # }
    return Response(
        status = 200,
        json = {
        "status":"success",
           # "base64_encoding": all_inputs['video'],
        "base64_encoding":result_video_base64_encoding
        # "base64_encoding":result_video_base64_encoding
    }
    )
if __name__ == "__main__":
    app.serve()
