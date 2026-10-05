#include <Arduino.h>
#include <FastLED.h>

#define numberOfLEDs 60
#define controlPin 5 // 使用するGPIOピン（環境に合わせて変更してください）

CRGB leds[numberOfLEDs];

uint8_t startIndex = 0; // グラデーションの位置を動かすための変数

void setup() {
  // ESP32-S3向けにFastLEDを初期化 (WS2812B / GRB)
  FastLED.addLeds<WS2812B, controlPin, GRB>(leds, numberOfLEDs);
  
  // 明るさ制限（0〜255）
  FastLED.setBrightness(100);
  
  // 初期化時の消灯処理
  FastLED.clear();
  FastLED.show();
}

void loop() {
  // 1つずつ色相（Hue）を少しずつずらしながらグラデーションを作成
  // fill_rainbow(配列, LEDの数, 開始色相, 各LED間の色相の差)
  fill_rainbow(leds, numberOfLEDs, startIndex, 255 / numberOfLEDs);

  // LEDに色を反映
  FastLED.show();

  // 開始位置を1進めて流れるようなアニメーションにする
  startIndex++;

  // アニメーションの速度調整（数値が小さいほど速く流れます）
  delay(20);
}

