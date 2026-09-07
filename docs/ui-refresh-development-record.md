# JARVIS UI刷新 開発記録

## 1. 概要

本記録は、テキストチャット中心だったJARVISの画面を、Neural Coreを主役とする
常駐AIインターフェースへ刷新した過程をまとめたものです。

刷新前は中央のチャット領域が画面の大部分を占め、状態、音声、Tool実行、ログが
個別に見えていました。刷新後は、全画面のCore空間の上へConversation、System Log、
Header、Voice Controlsを静かに重ね、状態を文字だけでなく色、粒子の流れ、収束・拡散、
発光で把握できる構成になっています。

開発では次の原則を一貫して維持しました。

- 既存のテキスト会話、Realtime音声、Tool実行、会話保存、Tray、Wake Wordを壊さない
- 表示状態と実際の接続・音声ライフサイクルを分離する
- pywebview内で完結し、ネットワーク依存のUI素材を追加しない
- WebGLに失敗しても従来のCSS表示へ戻れるようにする
- 常駐利用に備え、非表示時停止、FPS制御、DPR適応、明示的な解放を行う
- DOM IDとPython／JavaScript間の既存インターフェースを維持する

## 2. 完成時の画面構造

```text
Window
├─ Blue-black Spatial Background
│  ├─ 低コントラストの青・紫・青緑のAtmosphere
│  ├─ Perspective Grid
│  └─ Vignette
├─ Neural Core
│  ├─ GPU Particle Field
│  ├─ Selective Bloom
│  ├─ Volumetric Aura
│  ├─ State Transition
│  └─ Surface Resonance
├─ Core付随表示
│  ├─ JARVIS CORE / State
│  └─ Active Tool
└─ Overlay UI
   ├─ Header / Connection
   ├─ System Log
   ├─ Conversation / Text Input
   ├─ Voice Controls
   ├─ Error Notification
   └─ Status Bar
```

Neural Coreが常に主役です。左右の情報領域は独立したダッシュボードカードではなく、
Core空間へ溶け込む半透明のエッジオーバーレイとして配置しています。

## 3. 基礎UI刷新

### Phase 0 — 現状確認と互換性境界

実装前に既存のHTML、CSS、`static/script.js`、Realtimeイベント、会話保存処理を確認し、
変更してはいけない境界を整理しました。特にVoice ControlとText InputのDOM ID、
`window.jarvisRealtime.start(source, sessionId)`、Realtime cleanup順序を互換性境界としました。

大きくなっていた`script.js`は一括改修せず、表示責務から段階的に分割する方針としました。

### Phase 1〜3 — UI基盤、レイアウト、Visual System

表示専用State、DOM参照、Jarvis状態表示、System Log、Status Barをモジュール化しました。
これにより、接続処理を保持したまま表示だけを独立して更新できるようになりました。

画面にはHeader、System Log、Core領域、Conversation、Voice Controls、Status Barを導入し、
色、余白、Typography、Focus、Scrollbar、Reduced Motion、High Contrastを統一しました。
この段階のCoreは、WebGLが使えない場合にも残るCSSフォールバックでした。

### Phase 4 — 表示用State Machine

Realtimeイベントを`idle`、`connecting`、`listening`、`thinking`、`speaking`、`error`へ
変換する表示専用Controllerを追加しました。優先順位は次のとおりです。

```text
ERROR > LISTENING > SPEAKING > THINKING > CONNECTING > IDLE
```

LISTENINGをSPEAKINGより優先し、Jarvisが話している途中の割り込みも即座に見えるように
しています。Toolは重複実行を考慮して深さを数え、最後の処理が終わるまでTHINKINGを
維持します。切断、エラー、再接続では一時状態を必ずリセットします。

### Log表示クリア

System Log上部へ記号だけの小さなClearボタンを追加しました。削除対象はブラウザ内に
表示中の行だけです。Pythonログ、永続データ、Conversation履歴、今後追加されるイベントは
変更しません。

### Phase 5〜6 — 初期Three.js Coreと粒子アニメーション

ローカル同梱したThree.js r128で、CSS Coreの上にWebGL Coreを構築しました。初期実装は
球面粒子と内部Coreから始め、接続線は長距離で視認性を損なうため削除しました。
固体の内部球も廃止し、中心まで粒子で構成しました。

外周と内部の粒子へ異なる回転、位相、揺らぎを与え、均一な球ではなく流動する点群へ
調整しました。複数回の見た目確認を通じて半径、粒子解像度、色味、中心発光を調整し、
白飛びより状態色を優先しました。

### Phase 7〜9 — 性能、Audio Reactive、共通Conversation

常駐アプリ向けにIdle 20 FPS、Active 30 FPS、非表示時停止、Reduced Motion静止、
ResizeObserver、段階的DPR制御、WebGL resource cleanupを追加しました。

マイク入力とJarvis出力には別々のAnalyserNodeを使い、入力と出力が混線しない構成で
音量を取得しました。TextとVoiceのConversation表示は共通Rendererへ分離し、TEXT／VOICE、
SENDING／STREAMING／INTERRUPTED／FAILEDを同じ安全なDOM生成経路で表示しています。

### Phase 11 — 最終統合

音声・テキスト共通Chat、Tool表示、接続状態、エラー通知、System Log、Core状態を
`JarvisUI.state`へ接続しました。Conversation DOMは最大200件、System Logは最大100件に
制限し、永続データを削除せず表示だけをboundedにしています。

## 4. Visual Phase

### Visual Phase A — Shader Core

CPU側で粒子座標を毎フレーム更新するCoreを、独自`THREE.ShaderMaterial`によるGPU Particle
Fieldへ置き換えました。現在のGeometryは5,080個の不変Vertexを持ち、表面、内部体積、
中心へ流れる粒子、Cluster、軌道粒子を混在させています。

各粒子は基準位置、Seed、Size、Brightness、Speed、Phase、Layer種別を属性として保持します。
Vertex Shaderが回転、Curl Noise風変位、収束、漂流、State変位、Audio変形、距離補正Sizeを
計算し、Fragment Shaderが円形Edge、色付きHalo、Depth Fade、粒子ごとの輝度差を描画します。

高DPIでの品質改善ではDerivative Antialiasing、High Precision Fragment、Dithering、
複層の色付き輝度を導入しました。CPUはUniformだけを更新し、粒子Bufferは再構築しません。

### Visual Phase B — Bloom / Volumetric Glow

描画経路を`WebGLRenderer → RenderPass → UnrealBloomPass → Output`へ拡張しました。
BloomはCore用Canvas内だけに適用されるため、パネルや文字にはかかりません。

中心、高輝度粒子、Audio Peak、状態遷移、Tool Accentだけが強く発光するSelective Bloomと、
カメラ正面を向く複数の低透明度Layerによる疑似Volumetric Auraを追加しました。
色相を保つためThresholdを高め、Exposureを控えめにしています。

Auraの輪郭品質調整では、一度DPR依存の精密な円形Edgeへ変更した結果、積層境界が見えやすく
なりました。そのため広いAlpha Featherと従来のComposer color pathへ戻し、層の境目を
感じさせず徐々に透明になる表現へ仕上げました。

### Visual Phase C — State Transitions

状態ごとに色を即時変更する方式を廃止し、Target Profileへ0.4〜1.2秒で補間する方式へ
変更しました。回転、Noise、半径、吸引、Bloom、2色、Audio係数、粒子Size、Aura密度、
軌道同期、回転軸、内向きFlow、外向きWaveを共通の補間対象にしています。

- IDLE: 弱い対流、呼吸、低速回転
- CONNECTING: 中心収束、軌道同期、完了時に一度だけ安定Wave
- LISTENING: 外側から内側へ流入、Cyanの彩度上昇
- THINKING: 強い収束、高速内部Flow、Violet、Tool方向Flow
- SPEAKING: 中心から外側へ放出、Mint寄りの発光
- ERROR: 一度だけScatter、短いRed Accent、滑らかな回復

### Visual Phase D — Audio Ringの撤回とSurface Resonance

当初はCore外周に途切れた光弧を配置するAudio Ringを実装しました。しかし、独立した円や
波紋はCoreと別の装飾に見え、全体をゲームUI的かつ安価に見せる結果となりました。
この実装は削除し、Phase Cまでの外観へ戻しました。

再設計したSurface Resonanceは新しい輪郭を追加しません。既存粒子の密度、変位、彩度だけで
音声を表現します。LISTENINGでは外周から中心へ情報が流入し、SPEAKINGでは中心から表面へ
Energy Frontが進みます。無音Noise Gateと非対称Smoothingにより細かな震えを防いでいます。

### Visual Phase E — Spatial Background

画面全体へ青みのある暗い空間を設け、Perspective Grid、低速で変化する青・紫・青緑の
Atmosphere、Dust Band、Vignetteを追加しました。Coreより背景が目立たない濃度に調整し、
マウス追従は採用していません。

当初は遠景を示す星状点と背景Particle Fieldも加えましたが、Core粒子と視覚的に競合するため
最終的にすべて削除しました。現在の背景に点状要素はなく、色面、光量差、遠近Gridだけで
空間の奥行きを作っています。

pywebviewではEffectComposer出力がCanvasを不透明にするため、CSS背景だけでは見えないことも
実画面検証で判明しました。そこで同じWebGL Sceneの最背面へFull-frustum Planeを置き、
Composer経由でもAtmosphereが確実に表示される構成にしています。

### Visual Phase F — Panel / Control Polish

Headerを低くし、接続状態は文字より光点を主役にしました。System Logは時刻、種別、内容を
固定列で分け、INFO、TOOL、ERRORと新規Highlight、古い行の減光を追加しました。

ConversationはCard列からTimelineへ変更し、YOU／JARVIS、TEXT／VOICE、Streaming Cursor、
長文行長を整理しました。Voice操作はIcon中心としつつ、Tooltip、Accessible Name、Keyboard
Focusを維持しています。Tool表示には短縮名、細いProgress、Directional Pulse、完了Fadeを
追加しました。

初期の左右パネル感が強い構成からさらに修正し、Coreを全画面背景、LogとConversationを
左右端の静かなOverlayへ変更しました。HeaderもCore空間上に浮くTitleとして扱っています。

### Visual Phase G — Final Cinematic Polish

Window生成時だけ約1.65秒の起動演出を追加しました。背景、中心核、粒子収束、Core形成、
Interfaceの順で表示します。非表示からの復帰時には再生せず、Reduced Motionでは省略します。

接続成功、Tool開始・完了、Error、Chat追加、Log追加には短いMicro-interactionを割り当てました。
常時点滅や強い反復演出は避け、意味のある瞬間だけ光量とFlowが変化します。

## 5. `script.js`の分割結果

既存挙動を保持するため、Realtime、API、Conversation永続化の中心処理は`static/script.js`に
残し、表示責務を次のModuleへ移しました。

- `static/js/app-state.js`: 表示専用Shared State
- `static/js/dom.js`: DOM参照と契約
- `static/js/ui/ui-state-controller.js`: Realtime signalから表示状態への変換
- `static/js/ui/conversation-view.js`: Text／Voice共通Message描画
- `static/js/ui/system-log.js`: bounded System Log
- `static/js/ui/status-bar.js`: 接続・Latency表示
- `static/js/ui/integration-status.js`: ToolとError表示
- `static/js/audio/audio-reactive.js`: Input／Output audio level解析
- `static/js/core/*`: Core、Shader、Glow、背景、状態遷移、描画Lifecycle

この分割では通信のSource of Truthを移動していません。UI Moduleの障害がRealtime制御へ
影響しにくく、個別にテスト可能な境界を優先しています。

## 6. 性能と長時間稼働

- IDLE、CONNECTING、ERROR: 最大20 FPS
- LISTENING、THINKING、SPEAKING: 最大30 FPS
- DPR: 1.5／2.0／2.5を負荷に応じて段階変更
- 非表示Document: 描画停止
- Reduced Motion: 継続変位と一時Effectを停止
- Audio: Bufferを再利用し、終了時にNodeとAudioContextを解放
- WebGL: Geometry、Material、Texture、Composer target、Rendererを明示解放
- ResizeObserver、State購読、Event listener、Animation FrameをDispose時に解除
- Conversation表示最大200件、System Log表示最大100件
- 品質変更時もParticle Geometryを再生成しない

## 7. Responsive / Accessibility

標準幅974pxを基準にし、900px以下ではSystem Logを非表示、680px以下ではConversationを
下部Overlayへ移します。480pxでもText Input、Voice Control、主要状態を操作可能にしています。

すべての操作はKeyboardから実行でき、Icon ButtonにもAccessible NameとTooltipがあります。
Focus Visible、High Contrast、200%拡大、Live Region、`aria-busy`、Reduced Motionを考慮し、
装飾がErrorや操作状態を隠さないようにしています。

## 8. フォールバックと障害分離

```text
Shader Core + Composer
        ↓ 初期化／描画失敗
Direct WebGLRenderer
        ↓ WebGL初期化失敗
Legacy Three.js Core
        ↓ 利用不可
CSS Core
```

Post Processingの失敗は`CORE_BLOOM_FALLBACK`として記録し、通常Rendererへ戻ります。
Canvasは初期化成功後にだけ表示するため、失敗途中の黒画面を残しません。

## 9. 検証

各Phaseで`tests/test_ui_foundation.py`を中心にDOM契約、Script順序、State、Shader Uniform、
Cleanup、Responsive、Accessibility、Cache Versionを検証しました。ConversationとRealtimeの
関連Testも併用し、最終調整時点では全142件の自動Testが成功しています。

自動Testでは保証できない項目は`docs/ui-manual-verification.md`へ分離しました。実機では特に
次を確認します。

- 974px、900px、680px、480px、高DPI、200%拡大時の配置
- Microphone入力とJarvis出力でSurface Resonanceの方向が異なること
- Realtime切断・再接続後に状態やAnimationが残らないこと
- Composer失敗時、WebGL失敗時のFallback
- Tray、Window再表示、Wake Word、Speaker、Microphoneの実動作
- 長時間IDLE後のCPU／GPU負荷とMemory増加

## 10. 主な設計判断と学び

1. AIらしさは装飾の数ではなく、状態と運動の因果関係で作る。
2. 独立したRingや波紋は説明的だが、Coreの有機性を弱める場合がある。
3. 発光は白さではなく、状態色の彩度と周辺への減衰で表現する。
4. 高解像度化だけでは品質は上がらず、Alpha falloffとComposer color pathも重要である。
5. 背景の星状点は奥行きを作る一方、粒子Coreとは形状語彙が競合するため採用しない。
6. pywebviewと通常BrowserではComposer後の透明合成結果が異なるため実画面確認が必要である。
7. 表示Stateを通信Lifecycleから分離すると、大規模なVisual変更でも既存機能を維持しやすい。

## 11. 関連資料

- `docs/ui-architecture.md`: UI構成とPhase別の技術詳細
- `docs/ui-state-machine.md`: 状態優先順位とRealtime event mapping
- `docs/ui-manual-verification.md`: 手動確認手順
- `docs/visual-design-system.md`: 色、Motion、Layerの設計原則
- `docs/shader-architecture.md`: Shader、Bloom、Uniform、Resource lifecycle
- `docs/third-party-notices.md`: Three.jsとExamples由来Codeの表記

