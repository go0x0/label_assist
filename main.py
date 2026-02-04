import os
import sys
import subprocess
from dataclasses import dataclass
from PySide6.QtCore import QThread, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)


@dataclass
class ConvertRequest:
    video_path: str
    output_dir: str
    ffmpeg_path: str


class ConvertWorker(QThread):
    progress_changed = Signal(int)
    status_changed = Signal(str)
    finished_ok = Signal(int)
    failed = Signal(str)

    def __init__(self, request: ConvertRequest):
        super().__init__()
        self.request = request

    def run(self):
        try:
            self._convert_video()
        except Exception as exc:
            self.failed.emit(str(exc))

    def _convert_video(self):
        video_path = self.request.video_path
        output_dir = self.request.output_dir
        ffmpeg_path = self.request.ffmpeg_path

        if not os.path.exists(video_path):
            raise FileNotFoundError("视频文件不存在")

        os.makedirs(output_dir, exist_ok=True)

        if not ffmpeg_path or not os.path.isfile(ffmpeg_path):
            raise RuntimeError("未找到 ffmpeg，请安装后重试")

        self.progress_changed.emit(-1)
        self.status_changed.emit("开始转换...")

        output_pattern = os.path.join(output_dir, "img_%05d.jpg")
        cmd = [
            ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            video_path,
            "-vsync",
            "0",
            "-q:v",
            "2",
            "-start_number",
            "0",
            output_pattern,
        ]
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "ffmpeg 转换失败")

        frame_index = self._count_frames(output_dir)
        if frame_index > 999_999:
            raise RuntimeError("帧数超过 999999，已中止")
        self.progress_changed.emit(100)
        self.status_changed.emit("转换完成")
        self.finished_ok.emit(frame_index)

    def _count_frames(self, output_dir: str) -> int:
        try:
            return len(
                [
                    name
                    for name in os.listdir(output_dir)
                    if name.lower().endswith(".jpg") and name.startswith("img_")
                ]
            )
        except Exception:
            return 0


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("视频转图像 + Labelme")
        self.worker = None
        self.labelme_worker = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout()

        video_row = QHBoxLayout()
        video_label = QLabel("视频文件")
        self.video_path_input = QLineEdit()
        self.video_path_input.setReadOnly(True)
        self.choose_video_btn = QPushButton("选择视频")
        self.choose_video_btn.clicked.connect(self.choose_video)
        video_row.addWidget(video_label)
        video_row.addWidget(self.video_path_input)
        video_row.addWidget(self.choose_video_btn)
        layout.addLayout(video_row)

        output_row = QHBoxLayout()
        output_label = QLabel("输出目录")
        self.output_dir_input = QLineEdit()
        self.output_dir_input.setReadOnly(True)
        self.choose_output_btn = QPushButton("选择输出目录")
        self.choose_output_btn.clicked.connect(self.choose_output_dir)
        self.open_output_btn = QPushButton("打开输出目录")
        self.open_output_btn.clicked.connect(self.open_output_dir)
        output_row.addWidget(output_label)
        output_row.addWidget(self.output_dir_input)
        output_row.addWidget(self.choose_output_btn)
        output_row.addWidget(self.open_output_btn)
        layout.addLayout(output_row)

        action_row = QHBoxLayout()
        self.convert_btn = QPushButton("转换")
        self.convert_btn.clicked.connect(self.start_conversion)
        self.launch_labelme_btn = QPushButton("启动 Labelme")
        self.launch_labelme_btn.clicked.connect(self.launch_labelme)
        action_row.addWidget(self.convert_btn)
        action_row.addWidget(self.launch_labelme_btn)
        layout.addLayout(action_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        self.setLayout(layout)

    def choose_video(self):
        video_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择视频文件",
            "",
            "视频文件 (*.mp4 *.mov *.avi *.mkv *.m4v);;所有文件 (*)",
        )
        if not video_path:
            return

        self.video_path_input.setText(video_path)
        default_output = self._default_output_dir(video_path)
        self.output_dir_input.setText(default_output)

    def choose_output_dir(self):
        output_dir = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if not output_dir:
            return
        self.output_dir_input.setText(output_dir)

    def open_output_dir(self):
        output_dir = self.output_dir_input.text().strip()
        if not output_dir:
            self._alert("请先选择输出目录")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(output_dir))

    def start_conversion(self):
        video_path = self.video_path_input.text().strip()
        output_dir = self.output_dir_input.text().strip()
        if not video_path:
            self._alert("请先选择视频文件")
            return
        if not output_dir:
            self._alert("请先选择输出目录")
            return

        ffmpeg_path = self._find_ffmpeg()
        if not ffmpeg_path:
            self._alert("未找到 ffmpeg，请先安装或设置 FFMPEG_PATH")
            return

        if os.path.exists(output_dir) and os.listdir(output_dir):
            confirm = QMessageBox.question(
                self,
                "确认",
                "输出目录非空，是否继续转换并覆盖同名文件？",
                QMessageBox.Yes | QMessageBox.No,
            )
            if confirm != QMessageBox.Yes:
                return
        else:
            os.makedirs(output_dir, exist_ok=True)

        request = ConvertRequest(
            video_path=video_path,
            output_dir=output_dir,
            ffmpeg_path=ffmpeg_path,
        )
        self.worker = ConvertWorker(request)
        self.worker.progress_changed.connect(self.on_progress_changed)
        self.worker.status_changed.connect(self.on_status_changed)
        self.worker.finished_ok.connect(self.on_finished_ok)
        self.worker.failed.connect(self.on_failed)

        self.convert_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.status_label.setText("准备开始...")
        self.worker.start()

    def launch_labelme(self):
        uvx_path = self._find_uvx()
        if not uvx_path:
            self._alert(
                "未找到 uvx。请确认已安装 uvx 并加入 PATH，或设置环境变量 UVX_PATH 指向 uvx 可执行文件。"
            )
            return
        self._cleanup_dot_jpgs()
        self.status_label.setText("Labelme 启动中...")
        self.labelme_worker = LabelmeWorker(uvx_path)
        self.labelme_worker.failed.connect(self.on_labelme_failed)
        self.labelme_worker.started_ok.connect(self.on_labelme_started)
        self.labelme_worker.start()

    def on_progress_changed(self, value: int):
        if value < 0:
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(value)

    def on_status_changed(self, text: str):
        self.status_label.setText(text)

    def on_finished_ok(self, count: int):
        self._cleanup_dot_jpgs()
        self.convert_btn.setEnabled(True)
        self.status_label.setText(f"转换完成，共 {count} 帧")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)

    def on_failed(self, message: str):
        self.convert_btn.setEnabled(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self._alert(message)

    def on_labelme_started(self):
        self.status_label.setText("Labelme 已启动")

    def on_labelme_failed(self, message: str):
        self.status_label.setText("")
        self._alert(message)

    def _default_output_dir(self, video_path: str) -> str:
        folder = os.path.dirname(video_path)
        filename = os.path.basename(video_path)
        name, _ = os.path.splitext(filename)
        return os.path.join(folder, name)

    def _alert(self, message: str):
        QMessageBox.warning(self, "提示", message)

    def _cleanup_dot_jpgs(self):
        output_dir = self.output_dir_input.text().strip()
        if not output_dir or not os.path.isdir(output_dir):
            return
        try:
            for name in os.listdir(output_dir):
                if not (name.startswith(".") and name.lower().endswith(".jpg")):
                    continue
                path = os.path.join(output_dir, name)
                if os.path.isfile(path):
                    os.remove(path)
        except Exception:
            pass

    def _find_uvx(self) -> str | None:
        env_path = os.environ.get("UVX_PATH", "").strip()
        if env_path and os.path.isfile(env_path) and os.access(env_path, os.X_OK):
            return env_path

        candidate_paths = [
            os.path.expanduser("~/.cargo/bin/uvx"),
            os.path.expanduser("~/.local/bin/uvx"),
            "/usr/local/bin/uvx",
            "/opt/homebrew/bin/uvx",
        ]
        for candidate in candidate_paths:
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate

        return None

    def _find_ffmpeg(self) -> str | None:
        env_path = os.environ.get("FFMPEG_PATH", "").strip()
        if env_path and os.path.isfile(env_path) and os.access(env_path, os.X_OK):
            return env_path

        candidate_paths = [
            os.path.expanduser("~/.local/bin/ffmpeg"),
            "/usr/local/bin/ffmpeg",
            "/opt/homebrew/bin/ffmpeg",
            "/usr/bin/ffmpeg",
        ]
        for candidate in candidate_paths:
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate

        return None


class LabelmeWorker(QThread):
    started_ok = Signal()
    failed = Signal(str)

    def __init__(self, uvx_path: str):
        super().__init__()
        self.uvx_path = uvx_path

    def run(self):
        try:
            env = os.environ.copy()
            env["LANG"] = "zh_CN.UTF-8"
            env["LC_ALL"] = "zh_CN.UTF-8"
            env["LANGUAGE"] = "zh_CN.UTF-8"
            subprocess.Popen(
                [self.uvx_path, "labelme"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
            )
            self.started_ok.emit()
        except Exception as exc:
            self.failed.emit(f"启动失败：{exc}")


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(860, 220)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
