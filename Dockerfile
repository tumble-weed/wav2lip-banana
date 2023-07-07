
# Must use a Cuda version 10+
FROM pytorch/pytorch:1.11.0-cuda11.3-cudnn8-runtime
WORKDIR /home
# Install git
RUN apt-get update && apt-get install -y git curl
RUN apt-get install -y build-essential
RUN apt-get install ffmpeg -y
RUN apt update && apt install -y libsm6 libxext6 
RUN apt-get install -y libxrender-dev
RUN git clone https://github.com/tumble-weed/Wav2Lip.git

# RUN mv Wav2Lip /home/app

COPY . /home/app
#RUN mkdir -p /root/.cache/torch/checkpoints/
#COPY static/s3fd-619a316812.pth /root/.cache/torch/checkpoints//
# Install Sanic python packages
RUN pip3 install --upgrade pip

# Aniket: for readability renamed requirements.txt of wav2lip-banana to banana_requirements.txt
# RUN mv app/requirements.txt app/banana_requirements.txt
RUN pip3 install -r app/banana_requirements.txt


# wave2lip folder prep
RUN mv Wav2Lip/* /home/app
RUN pip3 install gdown
# Download wav2lip checkpoints
# https://drive.google.com/file/d/1QC6yiPGYxFmKpdQNXUgN3ZmyfZKvGk7-/view?usp=sharing
RUN gdown 1QC6yiPGYxFmKpdQNXUgN3ZmyfZKvGk7-
RUN mv s3fd-619a316812.pth /home/app/static/
# https://drive.google.com/file/d/1GkHG2UDiyOZik85mjN90CMo6Ktcv68Li/view?usp=sharing
RUN gdown 1GkHG2UDiyOZik85mjN90CMo6Ktcv68Li
RUN mv wav2lip.pth /home/app/static/

# Install wav2lip python packages
# RUN --mount=type=cache,target=/root/.cache/pip pip3 install -r app/requirements.txt
# Aniket: installing new_requirements.txt
RUN pip3 install -r app/requirements.txt

# Aniket: moved to new_requirements.txt
RUN pip3 install opencv-python==4.5.5.64

WORKDIR /home/app
# RUN python -c "import app; app.init()"
EXPOSE 8000

# CMD python3 -u server.py
# ENTRYPOINT ['sanic', 'server:app', '--host=0.0.0.0', '--port=8000', '--workers=4']
# CMD sanic server:server --host=0.0.0.0 --port=8000
CMD python3 -u app.py
