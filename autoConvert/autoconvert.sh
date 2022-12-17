#!/bin/bash
# Change Log
# 20221206 TM alt processing for sermons, noise removal makes music sound poor
# 20220826 TM set output dirs to /mnt/media 
# 20220813 TM added functions to set conversion options and wrapper
# 20221022 TM UPdate to audio filterchain, full auto with noise reduction
# ToDo
# Auto setup env of bp folders if not created

#####Config#######
# pickup path
bp=/mnt/media/AutoConvert/

# output path
op=/mnt/media/

# noise model
nm=/mnt/media/rnnoise-models-master/leavened-quisling-2018-08-31/lq.rnnn

#####Functions#####

# function to set convert options by file extension 

get_ffmpeg_opts(){
  #file_type,fname
  case $2 in
    *"Worship"*|*"worship"*) 
      echo $(set_worship_opts $1);;
    *"Sermon"*|*"sermon"*)
      echo $(set_sermon_opts $1);;
    *) 
      echo $(set_default_opts $1);;
  esac 
}

set_worship_opts(){
  case $1 in 
    #mp3|wav) echo "-c:a libmp3lame -b:a 48K -joint_stereo 1";;
    mp3|wav|flac) echo "-c:a libmp3lame -b:a 160K -joint_stereo 0";;
    avi|vbx|mp4) echo "-c:v h264 -b:v 1200k -vf scale=1080:trunc(ow/a/2)*2 -c:a libmp3lame -b:a 160k -joint_stereo 0";;
    *) echo "abc";;
   esac
}

set_sermon_opts(){
  case $1 in 
    #mp3|wav) echo "-c:a libmp3lame -b:a 48K -joint_stereo 1";;
    mp3|wav|flac) echo "-af acompressor,dynaudnorm,silenceremove=stop_periods=-1:stop_duration=2.3:stop_threshold=-33.5dB,afade=t=in:ss=0:d=1 -c:a libmp3lame -b:a 48K -joint_stereo 1";;
    avi|vbx|mp4) echo "-c:v h264 -b:v 1200k -vf scale=1080:trunc(ow/a/2)*2 -c:a libmp3lame -b:a 48k -joint_stereo 1";;
    *) echo "abc";;
   esac
}


set_default_opts(){
  case $1 in 
    #mp3|wav) echo "-c:a libmp3lame -b:a 48K -joint_stereo 1";;
    mp3|wav|flac) echo "-af acompressor,dynaudnorm,arnndn=m=$nm,silenceremove=stop_periods=-1:stop_duration=2.3:stop_threshold=-33.5dB,afade=t=in:ss=0:d=1 -c:a libmp3lame -b:a 48K -joint_stereo 1";;
    avi|vbx|mp4) echo "-c:v h264 -b:v 1200k -vf scale=1080:trunc(ow/a/2)*2 -c:a libmp3lame -b:a 48k -joint_stereo 1";;
    *) echo "abc";;
   esac
}


# function to set convert wrapper
get_ffmpeg_wrap(){
  case $1 in 
    mp3|wav|flac) echo "mp3";;
    avi|vbx|mp4) echo "mp4";;
    *) ;;
  esac
}

# determine output dir
get_output_dir(){
  t=$op
  case $1 in 
    *"Sunday_School"*)
      t+="Adult_Sunday_School";;
    *"Sermon"*)
      t+="Sermon";;
    *"Worship"*)
      t+="Worship";;
    *)
      t+="Other";;
  esac
  t+=/
  echo $t
}


#####QC/Sanity#####
# if ffmpeg is running abort
if pgrep ffmpeg >/dev/null; then 
        exit 0
fi

#####Main#####
# loop through the files in the target folder 
for file in $bp*.{avi,vbx,mp4,mp3,flac}; do
  # ensure the file exists and is not empty
  if [[ -s "$file" ]];then
    # parse file parts  
        fname=$(basename "$file")
          ext="${fname##*.}"
          fname="${fname%.*}"
    # now set the conversion options based upon file extension
    ffmpeg_opts="$(get_ffmpeg_opts $ext $fname)"
    ffmpeg_wrap="$(get_ffmpeg_wrap $ext)"
    # convert the file and move to destination directory as determined by output status
    ffmpeg -i "$file" $ffmpeg_opts "$(get_output_dir $fname)$fname.$ffmpeg_wrap" && mv "$file" ${bp}done/ || mv "$file" ${bp}failed/
    #echo $fname
    #echo "   $ffmpeg_opts"
    #echo $(get_output_dir $fname)
  fi
done
exit 0

