#!/bin/bash
workdir=$(dirname $0)
cd $workdir
workdir=$(pwd)
echo $workdir


CURRENT_TIME=$(date "+%Y%m%d_%H%M%S")

daemon_start(){
  cd $workdir
  nohup /data/xyzhao26/miniconda3/envs/voc/bin/python ${workdir}/app.py >> ${workdir}/logs/run.log 2>&1 &
}

daemon_stop(){
  pid=`ps -ef | grep "${workdir}/app.py" | grep -v grep |  awk '{print $2}'`
  echo $pid
  kill $pid
  sleep 2
  echo "Server Killed."
}

case "$1" in
  start)
    daemon_start
    ;;
  stop)
    daemon_stop
    ;;
  restart)
    daemon_stop
    daemon_start
    ;;
  *)
  echo "Usage: Services {start|stop|restart}"
  exit 1
esac
exit 0
