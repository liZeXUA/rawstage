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
  <!-- 可选：洞口定义 -->
  <holes>
    <hole id="hole_cave" x="800" y="900" width="140" height="40"
          sample_facility="cave_ground" cover_height="80" />
  </holes>
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

### 2.6 `<holes>` 洞口定义
洞是一种场景级空间特效元素，定义画布上的一个检测区域。当角色锚点（脚底）落入该区域时，引擎从背景设施图像中就地采样一块前景遮挡层覆盖在角色上方，模拟角色"进入洞穴/被地面吞没"的视觉效果，**无需额外美术素材**。

```xml
<holes>
  <hole id="hole_well" x="800" y="900" width="140" height="40"
        sample_facility="bg_ground" cover_height="60"
        depth_start="0.0" depth_end="1.0" />
</holes>
```
| 属性 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `id` | 是 | — | 洞的唯一标识 |
| `x` / `y` | 是 | — | 洞检测区域中心坐标（画布坐标） |
| `width` / `height` | 是 | — | 检测区域大小（角色锚点进入此范围即触发遮挡） |
| `sample_facility` | 是 | — | 用于采样遮挡块的前景/背景设施 ID（必须在 `<assets>` 中声明） |
| `cover_height` | 否 | `60` | 采样遮挡块的最大高度（像素），应与洞口上方边缘的地面纹理厚度匹配 |
| `depth_start` | 否 | `0.0` | 遮挡开始的深度阈值（depth_ratio 超过此值才开始绘制遮挡） |
| `depth_end` | 否 | `1.0` | 完全遮挡的深度阈值（depth_ratio 达到此值时遮挡块达到 cover_height 高度） |

**深度映射**：
- `depth_ratio` 为角色下沉程度，范围 [0, 1]
- 实际遮挡块高度 = `cover_height × clamp((depth_ratio - depth_start) / (depth_end - depth_start), 0, 1)`
- 被动检测时 `depth_ratio = (char.y - hole_top) / hole.height`

---

### 2.7 渲染层级与深度排序

所有可绘制元素（设施 + 角色）按以下规则排序绘制：

1. **按 `layer` 分组**：同一层名的元素归入一组
2. **层间按层名字母序绘制**：如 `background` → `front` → `midground` → `platform`
3. **层内按 `z` 升序绘制**：`z=0` 最先绘制（最远），`z=200` 最后绘制（最近）
4. **字幕始终在最顶层**（屏幕空间，不参与层级排序）

---

### 2.8 时间线事件总览
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
支持角色或设施的位移，控制方式可以是单目标或路径点（线性插值）。

**角色移动**（`character` 属性）：
```xml
<move character="alice" start="2.0" duration="1.5"
      to_x="600" to_y="800" easing="ease_in_out" />
```

**设施移动**（`facility` 属性）：
```xml
<move facility="cloud" start="0.0" duration="10.0"
      to_x="1200" to_y="300" easing="linear" />
```
`character` 和 `facility` 二选一（不可同时指定）。

**路径移动**（角色和设施均支持）：
```xml
<move character="alice" start="2.0" duration="2.0"
      path="300,800;450,700;600,800" easing="linear" />
```
使用 `path` 时 `to_x/to_y` 被忽略。`easing` 可选：`linear` / `ease_in` / `ease_out` / `ease_in_out`。

设施移动比角色简单：无进出场动画，无可见性管理，仅位置插值。

---

#### 🔄 旋转 `<rotate>`
控制角色或设施围绕锚点旋转。锚点默认取实体自身的 sprite 中心，也可指定固定坐标或绑定到另一个实体的中心。

```xml
<!-- 角色原地转圈 -->
<rotate character="alice" to_angle="360" start="2.0" duration="2.0" easing="ease_in_out" />

<!-- 多圈旋转（to_angle 可超过 360） -->
<rotate facility="windmill" to_angle="720" start="0.0" duration="5.0" easing="linear" />

<!-- 绕固定画布坐标旋转 -->
<rotate character="alice" to_angle="180" anchor_x="960" anchor_y="540"
        start="3.0" duration="1.5" easing="ease_out" />

<!-- 绕另一实体中心旋转（例如：剑绕角色头顶转圈） -->
<rotate facility="sword" to_angle="720" anchor_character="alice"
        start="1.0" duration="4.0" easing="linear" />

<!-- 一个角色绕另一个角色旋转 -->
<rotate character="bob" to_angle="-360" anchor_character="alice"
        start="2.0" duration="4.0" easing="ease_in_out" />
```

| 属性 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `character` | 二选一 | — | 旋转目标角色 ID |
| `facility` | 二选一 | — | 旋转目标设施 ID |
| `to_angle` | 是 | — | 目标旋转角度（度，正值=逆时针，支持超过 360 的多圈） |
| `start` | 是 | — | 开始时刻（秒） |
| `duration` | 是 | `0` | 持续时长（秒，0=瞬时切换） |
| `easing` | 否 | `linear` | `linear` / `ease_in` / `ease_out` / `ease_in_out` |
| `anchor_x` | 否 | 实体中心 | 固定锚点 X 坐标（画布坐标） |
| `anchor_y` | 否 | 实体中心 | 固定锚点 Y 坐标（画布坐标） |
| `anchor_character` | 否 | — | 锚点绑定到该角色中心（跟随移动） |
| `anchor_facility` | 否 | — | 锚点绑定到该设施中心（跟随移动） |

**锚点规则**：
- 未指定任何锚点 → 默认使用旋转目标自身的 sprite 中心
- 指定 `anchor_x` + `anchor_y` → 使用固定画布坐标
- 指定 `anchor_character` / `anchor_facility` → 使用该实体的 sprite 中心，且锚点跟随该实体移动
- 固定坐标和实体绑定不可同时指定

旋转与移动相互独立，可同时进行。

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

#### 🕳️ 角色进入洞 `<enter_hole>`
```xml
<!-- 主动驱动：引擎在 duration 内将 depth_ratio 从 0 线性增加到 1 -->
<enter_hole character="alice" hole="hole_well" start="3.0" duration="2.0" />
```
| 属性 | 必填 | 说明 |
|------|------|------|
| `character` | 是 | 角色 ID |
| `hole` | 是 | 引用的 `<hole>` ID |
| `start` | 是 | 开始时刻（秒） |
| `duration` | 是 | 下沉过程持续时长（秒），depth_ratio 在此时段内从 0→1 |

**工作机制**：
- `enter_hole` 事件仅驱动 `depth_ratio`（角色下沉程度），**不改变角色位置**。
- 角色位置由 `<move>` 或初始放置独立控制，配合 `<enter_hole>` 实现"走入洞中消失"。
- 也支持被动检测：即使没有 `<enter_hole>` 事件，角色锚点落入洞检测区域时引擎自动计算 depth_ratio 并绘制遮挡。

**典型组合用法**：
```xml
<!-- 角色走入洞口位置 -->
<move character="alice" to_x="800" to_y="900" start="3.0" duration="1.5" easing="ease_in" />
<!-- 进入洞的深度效果同步启动 -->
<enter_hole character="alice" hole="hole_well" start="3.0" duration="2.0" />
```

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
    <holes>
      <hole id="hole_cave" x="700" y="850" width="200" height="60"
            sample_facility="park" cover_height="120" />
    </holes>
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

      <!-- Bob 走入洞穴消失：move 控制位置，enter_hole 驱动遮挡 -->
      <move character="bob" to_x="700" to_y="850" start="7.0" duration="1.5" easing="ease_in" />
      <enter_hole character="bob" hole="hole_cave" start="7.0" duration="1.5" />

      <camera center_x="960" center_y="540" scale="1.0" start="8.5" duration="1.5" />

      <exit character="alice" method="fade_out" start="9.0" duration="0.8" />
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
