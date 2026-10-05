/*
 * 赤外線射的ゲーム (受信機) - 被弾音 / GAME OVER音 分割再生版
 */

#include <Arduino.h>
#include <FastLED.h>
#include <IRremoteESP8266.h>
#include <IRrecv.h>
#include <IRutils.h>

// --- MP3再生用ライブラリ ---
#include <FS.h>
#include <LittleFS.h>
#include "AudioFileSourceLittleFS.h"
#include "AudioGeneratorMP3.h"
#include "AudioOutputI2S.h"

// --- I2S (MAX98357A) ピン定義 ---
#define I2S_BCLK  4
#define I2S_LRC   5
#define I2S_DOUT  6

// --- ピン・LED定義 ---
#define numberOfLEDs 3
#define controlPin 5        // WS2812B信号ピン

const int IR_PIN = 7;       // IR受信機ピン
const int LED_SYSTEM = 0;   // SuperMini基板上LED

CRGB leds[numberOfLEDs];

// --- 設定 ---
const uint32_t HIT_CODE = 0xEF10FE01;
const unsigned long MIN_WAIT = 0;
const unsigned long MAX_WAIT = 0;
const unsigned long ACTIVE_TIMEOUT = 5000;
const unsigned long HIT_DISPLAY_TIME = 1500;
const unsigned long SYSTEM_BLINK_INTERVAL = 500;
const unsigned long TARGET_BLINK_INTERVAL = 100;
const unsigned long GAMEOVER_BLINK_INTERVAL = 150; 

// --- ライフ制の設定 ---
const int MAX_LIFE = 3;

// --- 状態管理 ---
enum GameState { WAITING, ACTIVE, HIT, GAME_OVER };
GameState gameState = WAITING;
GameState lastGameState = GAME_OVER;

int currentLife = MAX_LIFE;
int score = 0;
unsigned long lastTime = 0;
unsigned long waitDuration = 0;

// 非同期Lチカ用
unsigned long previousSystemBlinkTime = 0;
bool systemBlinkState = HIGH;

// 的LED用
unsigned long previousTargetBlinkTime = 0;
bool targetBlinkState = HIGH;

// IR検知フラッシュ用
unsigned long irDetectFlashTime = 0;

// IRオブジェクト
IRrecv irRecv(IR_PIN);
decode_results results;

// --- MP3再生オブジェクト ---
AudioGeneratorMP3 *mp3 = NULL;
AudioFileSourceLittleFS *file = NULL;
AudioOutputI2S *out = NULL;

// ★ 指定したMP3ファイルを再生する汎用関数
void playSound(const char *filename) {
  if (mp3 && mp3->isRunning()) {
    mp3->stop();
  }
  if (file) delete file;
  
  if (!LittleFS.exists(filename)) {
    Serial.printf("エラー: %s が見つかりません！\n", filename);
    return;
  }

  file = new AudioFileSourceLittleFS(filename);
  mp3->begin(file, out);
  Serial.printf("♪ [Sound Effect] Playing %s\n", filename);
}

// LED描画処理
void updateTargetLED(int life, bool ledOn) {
  if (!ledOn) {
    fill_solid(leds, numberOfLEDs, CRGB::Black);
  } else {
    switch (life) {
      case 3: fill_solid(leds, numberOfLEDs, CRGB::Green); break;  // 緑
      case 2: fill_solid(leds, numberOfLEDs, CRGB::Yellow); break; // 黄
      case 1: fill_solid(leds, numberOfLEDs, CRGB::Red); break;    // 赤
      default: fill_solid(leds, numberOfLEDs, CRGB::Black); break;
    }
  }
  FastLED.show();
}

void updateGameOverLED(bool ledOn) {
  if (ledOn) {
    fill_solid(leds, numberOfLEDs, CRGB::Magenta);
  } else {
    fill_solid(leds, numberOfLEDs, CRGB::Black);
  }
  FastLED.show();
}

void resetGame() {
  currentLife = MAX_LIFE;
  score = 0;
  gameState = WAITING;
  updateTargetLED(0, false);
  Serial.println("\n--- Game Reset. Life: 3 (Green) ---");
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  // --- LED初期化 ---
  FastLED.addLeds<WS2812B, controlPin, GRB>(leds, numberOfLEDs);
  FastLED.setBrightness(120);
  FastLED.clear();
  FastLED.show();

  pinMode(LED_SYSTEM, OUTPUT);
  digitalWrite(LED_SYSTEM, HIGH);

  // --- IR初期化 ---
  irRecv.enableIRIn();
  pinMode(IR_PIN, INPUT_PULLUP);

  // --- LittleFS & オーディオ出力初期化 ---
  if (!LittleFS.begin(true)) {
    Serial.println("LittleFSマウント失敗");
  } else {
    Serial.println("LittleFSマウント成功");
  }

  out = new AudioOutputI2S();
  out->SetPinout(I2S_BCLK, I2S_LRC, I2S_DOUT);
  out->SetRate(44100);
  out->SetGain(1.0); // 最大音量設定 (音割れする場合は 0.5 ~ 0.8 に下げてください)

  mp3 = new AudioGeneratorMP3();

  randomSeed(analogRead(10));
  lastTime = millis();
  waitDuration = random(MIN_WAIT, MAX_WAIT);

  Serial.println("\n--- Target Game Started (Multi-Sound Support) ---");
}

void loop() {
  unsigned long now = millis();

  // ==========================================
  // 0. MP3再生ループ処理（非同期デコード）
  // ==========================================
  if (mp3 && mp3->isRunning()) {
    if (!mp3->loop()) {
      mp3->stop();
      Serial.println("♪ 再生完了");
    }
  }

  // ==========================================
  // 1. 赤外線受信処理
  // ==========================================
  if (irRecv.decode(&results)) {
    uint32_t receivedCode = results.value;

    digitalWrite(LED_SYSTEM, LOW); 
    irDetectFlashTime = now;

    String protocolName = typeToString(results.decode_type);
    Serial.printf("[IR RX] Protocol: %-10s | Code: 0x%08X", protocolName.c_str(), receivedCode);

    if (receivedCode == HIT_CODE) {
      Serial.print(" <--- ★ MATCHED HIT CODE!");
    }
    Serial.println();

    // ヒット判定
    if (gameState == ACTIVE && receivedCode == HIT_CODE) {
      currentLife--;
      score++;

      if (currentLife > 0) {
        // ★ ライフが残っている場合は被弾音を再生
        playSound("/hit.mp3");
        gameState = HIT;
        Serial.printf("★ HIT! Score: %d | Life: %d\n", score, currentLife);
      } else {
        // ★ ライフがゼロになった場合はゲームオーバー音を再生
        playSound("/gameover.mp3");
        gameState = GAME_OVER;
        Serial.printf("\n★★★ GAME OVER ★★★\nFinal Score: %d\n", score);
      }
      lastTime = now;
    }

    irRecv.resume();
  }

  // ==========================================
  // 2. システムLED（通常時: Lチカ / 検知時: フラッシュ）
  // ==========================================
  if (now - irDetectFlashTime < 100) {
    digitalWrite(LED_SYSTEM, LOW);
  } else {
    if (now - previousSystemBlinkTime >= SYSTEM_BLINK_INTERVAL) {
      previousSystemBlinkTime = now;
      systemBlinkState = !systemBlinkState;
      digitalWrite(LED_SYSTEM, systemBlinkState);
    }
  }

  // ==========================================
  // 3. ゲームロジック & LED制御
  // ==========================================
  switch (gameState) {
    case WAITING:
      if (lastGameState != WAITING) {
        updateTargetLED(0, false);
        lastGameState = WAITING;
      }
      if (now - lastTime >= waitDuration) {
        gameState = ACTIVE;
        lastTime = now;
        Serial.println("Target appeared!");
      }
      break;

    case ACTIVE:
      if (lastGameState != ACTIVE) {
        updateTargetLED(currentLife, true);
        lastGameState = ACTIVE;
      }
      if (now - lastTime >= ACTIVE_TIMEOUT) {
        gameState = WAITING;
        lastTime = now;
        waitDuration = random(MIN_WAIT, MAX_WAIT);
        Serial.println("Missed...");
      }
      break;

    case HIT:
      lastGameState = HIT;
      if (now - previousTargetBlinkTime >= TARGET_BLINK_INTERVAL) {
        previousTargetBlinkTime = now;
        targetBlinkState = !targetBlinkState;
        updateTargetLED(currentLife, targetBlinkState == LOW);
      }
      if (now - lastTime >= HIT_DISPLAY_TIME) {
        gameState = WAITING;
        lastTime = now;
        waitDuration = random(MIN_WAIT, MAX_WAIT);
      }
      break;

    case GAME_OVER:
      lastGameState = GAME_OVER;

      if (now - previousTargetBlinkTime >= GAMEOVER_BLINK_INTERVAL) {
        previousTargetBlinkTime = now;
        targetBlinkState = !targetBlinkState;
        updateGameOverLED(targetBlinkState);
      }

      if (now - lastTime >= 5000) {
        resetGame();
        lastTime = now;
        waitDuration = random(MIN_WAIT, MAX_WAIT);
      }
      break;
  }
}



