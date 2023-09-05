sudo apt-get update
sudo apt-get install -y build-essential libssl-dev libffi-dev python3-dev

python3 -m venv yun
source yun/bin/activate

pip3 install requests
pip3 install pyDes
pip3 install apscheduler

nohup python ./yunrun.py > ./output.log &

echo "$(date): YunRun is running!"