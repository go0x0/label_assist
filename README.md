# Label Assist

## 本地运行
1. 创建虚拟环境（推荐使用提供的脚本）
   - 使用脚本（自动创建并安装依赖）：

```
./setup_env.sh
```

   - 或手动创建并激活：

```
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```
2. 启动
   - `python main.py`

## 打包（macOS）
- 运行 `./build.sh`
- 产物在 `dist/LabelAssist`

## 说明
- 视频逐帧输出命名为 `img_000000.jpg` 格式。
- 当输出目录非空时会提示是否继续。
- “启动 Labelme” 会尝试调用 `uvx labelme`，请确保 uvx 已安装并在 PATH 中。
