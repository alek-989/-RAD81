# This work is licensed under the MIT license.
# Copyright (c) 2013-2023 OpenMV LLC. All rights reserved.
# https://github.com/openmv/openmv/blob/master/LICENSE
#
# Hello World Example
#
# Welcome to the OpenMV IDE! Click on the green run arrow button below to run the script!

import sensor, image, time, os, tf, uos, gc
from machine import LED
import network
import json

from mqtt import MQTTClient

SSID = "123456"
KEY = "987654321"

print("尝试连接 Wi-Fi...")
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(SSID, KEY)
while not wlan.isconnected():
    print("等待 Wi-Fi 连接...")
    time.sleep_ms(1000)
print("Wi-Fi 连接成功！")

print("尝试启动 MQTT 客户端...")
client = MQTTClient("openmv", "broker.hivemq.com", port=1883)
try:
    client.connect()
    print("MQTT 客户端连接成功！")
except Exception as e:
    print(f"MQTT 连接失败: {e}")
    client = None

sensor.reset()
sensor.set_pixformat(sensor.RGB565)
sensor.set_framesize(sensor.QVGA)
sensor.set_windowing((240, 240))
sensor.skip_frames(time=2000)

net = None
labels = None
led = LED("LED_BLUE")

try:
    net = tf.load("trained.tflite", load_to_fb=uos.stat('trained.tflite')[6] > (gc.mem_free() - (64*1024)))
except Exception as e:
    raise Exception('无法加载 "trained.tflite"，请确认文件已复制到设备。 (' + str(e) + ')')

try:
    labels = [line.rstrip('\n') for line in open("labels.txt")]
except Exception as e:
    raise Exception('无法加载 "labels.txt"，请确认文件已复制到设备。 (' + str(e) + ')')

clock = time.clock()


PUBLISH_INTERVAL = 5          # 消息发送间隔（秒）
SCORING_PERIOD_DURATION = 30  # 评分周期总时长（秒）
SCORE_DEDUCTION = 20          # 每次扣分的分值

total_score = 100             # 初始总分
message_count_in_period = 0   # 周期内发送消息的次数
last_publish_time = 0         # 上次发送消息的时间戳
scoring_period_start_time = time.time() # 评分周期开始时间
game_over = False             # 评分周期是否结束的标志

while(True):
    clock.tick()
    img = sensor.snapshot()

    # --- 首先，检查评分周期是否已经结束 ---
    elapsed_time = time.time() - scoring_period_start_time
    if not game_over and elapsed_time > SCORING_PERIOD_DURATION:
        game_over = True # 标记周期结束
        led.off()
        print("="*30)
        print(f"评分周期（{SCORING_PERIOD_DURATION}秒）已结束!")
        print(f"最终整洁度得分: {total_score}")
        print(f"周期内共检测到 {message_count_in_period} 次杂乱。")
        print("="*30)

        # 发送最终的得分报告
        if client:
            try:
                score_data = {
                                    "student_id": "231549999",
                                    "bench_id": "66",
                                    "cleanliness_score": total_score
                                }
                client.publish("mqtt/test/result", json.dumps(score_data))
                print("最终得分报告已通过 MQTT 发布。")
            except Exception as e:
                print(f"错误: MQTT 发布最终得分失败: {e}")

    # --- 如果评分周期还未结束，则执行检测逻辑 ---
    if not game_over:
        detection_found = False
        for obj in net.classify(img, min_scale=1.0, scale_mul=0.8, x_overlap=0.5, y_overlap=0.5):
            predictions_list = list(zip(labels, obj.output()))
            if predictions_list and predictions_list[0][1] > 0.95:
                detection_found = True
                img.draw_rectangle(obj.rect(), color=(255,0,0)) # 直接画红框
                # 找到一个就可以跳出当前帧的检测，提高效率
                break

        if detection_found:
            led.on()
            print("检测到物体...")

            current_time = time.time()
            if (current_time - last_publish_time) > PUBLISH_INTERVAL:
                print(f"距离上次发送已超过 {PUBLISH_INTERVAL} 秒，记录一次并扣分。")

                # 更新分数和计数
                total_score -= SCORE_DEDUCTION
                if total_score < 0: total_score = 0 # 分数不能为负
                message_count_in_period += 1
                print(f"当前得分: {total_score}, 已检测次数: {message_count_in_period}")

                # 发送检测消息
                message_to_send = "there are some rubbish"
                if client:
                    try:
                        client.publish("mqtt/test/result", message_to_send)
                        print(f"MQTT 消息已发布: {message_to_send}")
                    except Exception as e:
                        print(f"错误: MQTT 发布消息失败: {e}")

                # 更新时间戳
                last_publish_time = current_time
        else:
            led.off()
            print("环境整洁...")
    else:
        # 评分结束后，程序进入空闲状态，只做延时，降低CPU占用
        time.sleep_ms(500)
