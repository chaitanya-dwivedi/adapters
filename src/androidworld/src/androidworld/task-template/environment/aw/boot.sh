#!/bin/bash
# Idempotent: boots the headless emulator + AndroidWorld daemon (which initializes the task).
# Safe to call repeatedly (entrypoint, solve.sh, test.sh and the agent may all call it).
mkdir -p /logs/aw
if pgrep -f "aw/daemon.py" >/dev/null; then exit 0; fi
exec 9>/tmp/aw_boot.lock; flock -n 9 || exit 0
(
  ACCEL="-accel off"
  if [ -e /dev/kvm ]; then ACCEL="-accel on"; fi
  adb kill-server; adb start-server
  nohup emulator @"${EMULATOR_NAME}" -no-window -no-snapshot -no-boot-anim -noaudio \
      -memory 4096 $ACCEL -gpu swiftshader_indirect -grpc 8554 > /logs/aw/emulator.log 2>&1 &
  for i in $(seq 1 150); do
    [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ] && break
    sleep 4
  done
  adb root || true
  adb shell input keyevent 82 || true
  adb shell "settings put global window_animation_scale 0.0; settings put global transition_animation_scale 0.0; settings put global animator_duration_scale 0.0"
  adb shell "settings put global hidden_api_policy_pre_p_apps 1; settings put global hidden_api_policy_p_apps 1; settings put global hidden_api_policy 1"
  nohup python3 /opt/aw/daemon.py > /logs/aw/daemon.log 2>&1 &
) 9>&-
