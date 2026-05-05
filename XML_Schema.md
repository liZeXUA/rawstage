一套专用于"LLM 直出演出指令"的 XML Schema，命名为 **ComicDirector ML v1.0**。  
该 Schema 全面覆盖角色控制、镜头运动、对话字幕、切换表情等需求，同时对 LLM 友好，支持微调时学习空间连贯性与导演风格。

---

## 一、设计总则

| 原则 | 说明 |
|------|------|
| **统一画布坐标系** | 虚拟画布固定为 **1920×1080**，所有坐标均以此为基准。角色默认锚点为**图片下边缘中心（脚底）**，方便落地对齐。 |
| **绝对时间线** | 每个场景以 `0s` 为起始，所有事件用 `start`（单位：秒）+ `duration` 控制，确保可逐帧精确重现。 |
| **分层描述** | 场景 → 初始化环境 → 事件序列（enter / exit / move / dialogue / expression / camera 等），结构清晰。 |
| **镜头模型** | 镜头定义视口：`center_x, center_y` 为视口中心在画布上的坐标，`scale` 为缩放系数（1.0 = 全画布 1920×1080）。 |
| **层级与深度** | 每个资产声明 `layer`（层名）和 `z`（深度 0-200）。同层内按 z 升序绘制（z 越大越靠近观众）。层之间按层名字母序绘制。字幕始终在最顶层。 |
| **可扩展性** | 预留音频、特效、场景过渡等节点，后续可平滑升级。 |

---

## 二、元素层级与属性规范

### 根元素 `<comic_script>`
```xml
<comic_script version="1.0">
  <meta ... />
  <assets ... />
  <scene ... > ... </scene>
  <transition ... />
  <scene ... > ... </scene>
</comic_script>
```
| 属性 | 必填 | 说明 |
|------|------|------|
| `version` | 是 | 固定 `"1.0"` |

---

### 2.1 `<meta>` （元信息）
```xml
<meta title="示例剧集" author="AI导演" created="2026-05-03" />
```
子元素可扩展，初期直接使用属性。

---

### 2.2 `<assets>` （资产声明）
集中管理所有可引用的资源，避免重复路径，方便 LLM 记忆。

```xml
<assets>
  <!-- 角色：可移动、可动画、可切换表情 -->
  <character id="alice" name="Alice" src="chars/alice_default.png" layer="platform" z="100" />
  <character id="bob" name="Bob" src="chars/bob_default.png" layer="platform" z="110" />

  <!-- 设施（道具/背景元素）：静态物体，不可动画 -->
  <facility id="sky" src="bg/sky.png" layer="background" z="0" />
  <facility id="mountain" src="bg/mountain.png" layer="background" z="10" />
  <facility id="tree" src="props/tree.png" layer="front" z="180" />

  <!-- 表情：绑定到角色，通过 id 引用切换立绘 -->
  <expression character="alice" id="alice_angry" src="chars/alice_angry.png" />

  <!-- 音频 -->
  <audio id="bgm_calm" src="audio/calm_theme.mp3" />
</assets>
```

#### character
| 属性 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `id` | 是 | — | 角色唯一标识 |
| `name` | 否 | `id` 值 | 显示名称 |
| `src` | 是 | — | 默认立绘图片路径（PNG，RGBA） |
| `layer` | 否 | `platform` | 渲染层名 |
| `z` | 否 | `100` | 层内深度（0-200，越大越近） |

#### facility
| 属性 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `id` | 是 | — | 设施唯一标识 |
| `src` | 是 | — | 图片路径（PNG，RGBA） |
| `layer` | 否 | `midground` | 渲染层名 |
| `z` | 否 | `50` | 层内深度（0-200，越大越近） |

#### expression
| 属性 | 必填 | 说明 |
|------|------|------|
| `id` | 是 | 表情唯一标识（供 `expression` 事件引用） |
| `character` | 是 | 所属角色 ID |
| `src` | 是 | 表情图片路径 |

#### audio
| 属性 | 必填 | 说明 |
|------|------|------|
| `id` | 是 | 音频唯一标识 |
| `src` | 是 | 音频文件路径 |

> **移除 `<background>`**：不再需要独立的背景资产类型。远山、天空、云层等背景元素使用 `<facility layer="background">` 定义。

---

### 2.3 脚本块模型：`<scene>` 与 `<transition>`
一个视频由若干个 `<scene>` 和可选的 `<transition>`（场景过渡）交替组成，两者均作为 `<comic_script>` 的直接子元素（顶层块）。解析后形成 `list[Scene | Transition]` 序列。

**验证规则**：
- 脚本不能以 `<transition>` 开头或结尾
- 不允许两个 `<transition>` 连续出现

#### `<scene>` （单一场次）
定义初始镜头、角色和设施的初始点位，然后按时间线播放事件。
```xml
<scene id="1" duration="8.5">
  <initial_camera center_x="960" center_y="540" scale="1.0" />
  <initial_facilities>
    <place facility="sky" x="960" y="540" />
    <place facility="tree" x="200" y="700" />
  </initial_facilities>
  <initial_characters>
    <place character="alice" x="300" y="800" />
  </initial_characters>
  <timeline>
    <!-- 一系列事件 -->
  </timeline>
</scene>
```
| scene 属性 | 必填 | 说明 |
|------------|------|------|
| `id` | 是 | 场景序号或标识 |
| `duration` | 是 | 场景总时长（秒），用于校验 |

> **移除 `background` 属性**：场景不再指定单一背景。所有背景元素通过 `<initial_facilities>` 中的 `<place>` 放置。

---

### 2.4 镜头初始化 `<initial_camera>`
```xml
<initial_camera center_x="960" center_y="540" scale="1.0" />
```
镜头随后可通过事件动态改变。若省略，默认值如上。

---

### 2.5 初始摆放 `<initial_characters>` / `<initial_facilities>`
两者使用相同的 `<place>` 结构：

| 属性 | 必填 | 说明 |
|------|------|------|
| `character` | 是* | 角色 ID（在 `<initial_characters>` 中使用） |
| `facility` | 是* | 设施 ID（在 `<initial_facilities>` 中使用） |
| `x` / `y` | 是 | 画布坐标（脚底锚点） |

`<initial_facilities>` 中的设施在整个场景期间位置不变（无动画）。未出现在 `<initial_characters>` 中的角色默认为**未入场状态**（不渲染）。

---

### 2.6 渲染层级与深度排序

所有可绘制元素（设施 + 角色）按以下规则排序绘制：

1. **按 `layer` 分组**：同一层名的元素归入一组
2. **层间按层名字母序绘制**：如 `background` → `front` → `midground` → `platform`
3. **层内按 `z` 升序绘制**：`z=0` 最先绘制（最远），`z=200` 最后绘制（最近）
4. **字幕始终在最顶层**（屏幕空间，不参与层级排序）

---

### 2.7 时间线事件总览
所有事件共享 `start` 和 `duration`（单位秒），均位于 `<timeline>` 内。

---

#### 🎬 角色出场 `<enter>`
```xml
<enter character="bob" method="slide_left" start="1.0" duration="0.8"
       target_x="800" target_y="800" />
```
| 属性 | 说明 |
|------|------|
| `method` | `fade_in` / `slide_left` / `slide_right` / `slide_up` / `slide_down` / `pop_in` |
| `target_x, target_y` | 出场结束后的位置（若省略则使用 `place` 预定义位置） |

**各 method 效果说明**：
- `fade_in`：原地淡入（透明度 0→1）
- `slide_left`：从左侧屏幕外滑入目标位置
- `slide_right`：从右侧屏幕外滑入目标位置
- `slide_up`：从下方屏幕外滑入目标位置
- `slide_down`：从上方屏幕外滑入目标位置
- `pop_in`：原地弹出（缩放 0→1.1→1.0，带弹性过冲效果）

---

#### 👋 角色退场 `<exit>`
```xml
<exit character="alice" method="slide_right" start="7.0" duration="0.6" />
```
| 属性 | 说明 |
|------|------|
| `method` | `fade_out` / `slide_left` / `slide_right` / `slide_up` / `slide_down` |

退场动画结束后角色从画布移除（不可见）。`fade_out` 渐变透明退出，其他 slide 方法沿指定方向滑出屏幕。

---

#### 🚶 移动 `<move>`
支持单目标或路径点（线性插值）。
```xml
<move character="alice" start="2.0" duration="1.5"
      to_x="600" to_y="800" easing="ease_in_out" />
```
若需曲线移动，使用 `path` 属性（分号分隔坐标）：
```xml
<move character="alice" start="2.0" duration="2.0"
      path="300,800;450,700;600,800" easing="linear" />
```
此时 `to_x/to_y` 忽略。`easing` 可选：`linear` / `ease_in` / `ease_out` / `ease_in_out`。

---

#### 💬 底部字幕 `<dialogue>`

对话以**底部字幕**形式显示，固定在画布底部中央（`y=1080 - img_height - 60`），不跟随角色或镜头。支持两种形式：纯文本和富文本（`<span>` 子元素）。

**纯文本形式**（向后兼容）：
```xml
<dialogue character="alice" start="3.0" duration="3.0"
          text="这个地方真美！" />
```

**富文本形式**（通过 `<span>` 子元素混合样式）：
```xml
<dialogue character="alice" start="3.0" duration="3.0"
          font_size="48" color="#FFFFFF"
          outline_width="2" outline_color="#333333">
  <span color="#00FF00" italic="true">绿色斜体，</span>
  <span color="#FF0000" underline="true" bold="true">红色粗体下划线</span>
</dialogue>
```
若同时存在 `text` 属性和 `<span>` 子元素，优先使用 `<span>`。

| 属性 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `character` | 是 | — | 发言角色 ID |
| `text` | 否* | — | 纯文本内容（无 `<span>` 子元素时必填） |
| `start` | 是 | — | 字幕出现时刻（秒） |
| `duration` | 是 | — | 字幕持续时长（秒） |
| `font` | 否 | 系统 CJK 字体 | 字体文件路径 |
| `font_size` | 否 | `40` | 默认字号（像素） |
| `color` | 否 | `#FFFFFF` | 默认文字颜色（hex RGB/RGBA） |
| `outline_width` | 否 | `3` | 文字描边宽度（像素） |
| `outline_color` | 否 | `#000000` | 文字描边颜色（hex RGB/RGBA） |

**`<span>` 子元素属性**（每个 span 可覆盖以上默认值）：

| 属性 | 说明 |
|------|------|
| `color` | 文字颜色（hex，如 `#FF0000`） |
| `size` | 字号覆盖 |
| `italic` | `"true"` / `"false"` |
| `underline` | `"true"` / `"false"` |
| `bold` | `"true"` / `"false"` |
| `font` | 字体文件路径覆盖 |

**渲染规则**：
- 字幕固定于**画布底部居中**（不跟随镜头），底部留白 60px
- 多个 `<span>` 水平拼接，基线对齐
- 描边通过在所有方向绘制偏移文字实现；粗体通过水平微偏移模拟；斜体通过水平 shear 变换实现；下划线绘制于文字底部下方
- 不使用气泡框，纯文字展示，风格简洁原始

---

#### 😠 表情切换 `<expression>`
```xml
<expression character="alice" set="alice_angry" start="4.5" />
```
引用 `assets` 中定义的 `expression` ID，立即切换角色立绘为对应表情图片。表情切换为瞬时操作（无 `duration` 属性），一旦 `t >= start` 即生效并保持到场景结束或被后续表情覆盖。

---

#### 📷 镜头运动 `<camera>`
支持推拉摇移，可组合使用。
```xml
<!-- 摇镜到某角色（自动计算中心） -->
<camera target="bob" scale="1.2" start="2.0" duration="1.5" easing="ease_out" />

<!-- 手动指定视口中心 + 缩放 -->
<camera center_x="500" center_y="600" scale="0.8" start="5.0" duration="2.0" />
```
若同时指定 `target` 和坐标，优先 `target`。`scale` 可单独改变（推拉）。

---

#### 🔊 音效 / 背景音乐 `<audio>`
```xml
<audio ref="bgm_calm" action="play" start="0" duration="0" loop="true" volume="0.6" />
<audio ref="sfx_jump" action="play_once" start="3.2" />
```
| 属性 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `ref` | 是 | — | 引用 `assets` 中音频 `id` |
| `action` | 否 | `play` | `play`（可循环背景音）或 `play_once`（一次性音效，不循环） |
| `start` | 是 | — | 开始时刻（秒） |
| `duration` | 否 | `0` | 播放持续时长（秒，0 表示完整播放） |
| `loop` | 否 | `false` | `"true"` / `"false"`，是否循环播放 |
| `volume` | 否 | `1.0` | 音量系数（0.0-1.0） |

音频通过 ffmpeg 混音合成到最终视频中，支持延迟（`adelay`）、裁剪（`atrim`）、音量调节（`volume`）和混合（`amix`）。

---

#### ⏱️ 场景过渡 `<transition>`
作为 `<comic_script>` 的直接子元素，位于两个 `<scene>` 之间。过渡期间场景 A 和场景 B 均处于播放状态，引擎混合两者画面。
```xml
<transition type="fade" duration="0.5" />
```
| 属性 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `type` | 否 | `fade` | `fade` / `dissolve`（交叉淡入淡出）、`wipe_left`（B 从左向右擦除 A）、`wipe_right`（B 从右向左擦除 A） |
| `duration` | 是* | — | 过渡持续时长（秒） |

> **注意**：`fade` 和 `dissolve` 实现相同（均匀 alpha 混合），两者均可用。

---

## 三、完整示例 XML

```xml
<?xml version="1.0" encoding="UTF-8"?>
<comic_script version="1.0">
  <meta title="公园初遇" author="AI导演" />

  <assets>
    <!-- 角色（layer=platform 表示站立层） -->
    <character id="alice" name="Alice" src="alice.png" layer="platform" z="100" />
    <character id="bob" name="Bob" src="bob.png" layer="platform" z="110" />
    <expression character="alice" id="alice_shy" src="alice_shy.png" />

    <!-- 背景设施（layer=background） -->
    <facility id="park" src="park_bg.jpg" layer="background" z="0" />
    <facility id="street" src="street_bg.jpg" layer="background" z="0" />

    <!-- 前景设施（layer=front，z 值大于角色，遮挡角色） -->
    <facility id="tree_left" src="tree.png" layer="front" z="180" />

    <audio id="bgm_peace" src="peace.mp3" />
  </assets>

  <scene id="1" duration="10.0">
    <initial_camera center_x="960" center_y="540" scale="1.0" />
    <initial_facilities>
      <place facility="park" x="960" y="540" />
      <place facility="tree_left" x="150" y="700" />
    </initial_facilities>
    <initial_characters>
      <place character="alice" x="400" y="800" />
    </initial_characters>

    <timeline>
      <audio ref="bgm_peace" action="play" start="0" loop="true" volume="0.5" />

      <enter character="bob" method="slide_left" start="0.5" duration="0.8"
             target_x="1100" target_y="800" />

      <move character="bob" start="2.0" duration="2.0"
            to_x="700" to_y="800" easing="ease_in_out" />

      <camera target="bob" scale="1.1" start="2.0" duration="2.0" easing="ease_out" />

      <dialogue character="alice" start="4.5" duration="2.5"
                text="你好，今天天气真好！" />

      <expression character="alice" set="alice_shy" start="6.0" />

      <move character="alice" start="6.5" duration="1.0"
            to_x="450" to_y="780" easing="linear" />

      <camera center_x="960" center_y="540" scale="1.0" start="8.0" duration="1.5" />

      <exit character="bob" method="slide_right" start="8.5" duration="0.8" />
    </timeline>
  </scene>

  <!-- 过渡为顶层元素，位于两个 scene 之间 -->
  <transition type="fade" duration="0.5" />

  <scene id="2" duration="6.0">
    <initial_camera center_x="960" center_y="540" scale="1.0" />
    <initial_facilities>
      <place facility="street" x="960" y="540" />
    </initial_facilities>
    <initial_characters>
      <place character="alice" x="500" y="800" />
      <place character="bob" x="1100" y="800" />
    </initial_characters>

    <timeline>
      <dialogue character="alice" start="0.5" duration="3.0"
                font_size="48" color="#FFFFFF"
                outline_width="2" outline_color="#333333">
        <span color="#FFD700" bold="true">Bob：</span>
        <span>明天还在这里见面吧。</span>
      </dialogue>

      <exit character="alice" method="fade_out" start="4.0" duration="0.8" />
      <exit character="bob" method="slide_left" start="4.5" duration="0.6" />
    </timeline>
  </scene>
</comic_script>
```

---
