import os
import sys
import shutil
import subprocess
from dataclasses import dataclass

import cv2
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

        if not os.path.exists(video_path):
            raise FileNotFoundError("视频文件不存在")

        os.makedirs(output_dir, exist_ok=True)

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError("无法打开视频文件")

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if total_frames > 0:
            self.progress_changed.emit(0)
        else:
            self.progress_changed.emit(-1)

        frame_index = 0
        self.status_changed.emit("开始转换...")
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            if frame_index >= 999_999:
                cap.release()
                raise RuntimeError("帧数超过 999999，已中止")

            filename = f"img_{frame_index:06d}.jpg"
            output_path = os.path.join(output_dir, filename)
            success = cv2.imwrite(output_path, frame)
            if not success:
                cap.release()
                raise RuntimeError("图像写入失败")

            frame_index += 1
            if total_frames > 0:
                progress = int(frame_index / total_frames * 100)
                self.progress_changed.emit(progress)

        cap.release()
        self.progress_changed.emit(100)
        self.status_changed.emit("转换完成")
        self.finished_ok.emit(frame_index)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("视频转图像 + Labelme")
        self.worker = None
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

        request = ConvertRequest(video_path=video_path, output_dir=output_dir)
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
        uvx_path = shutil.which("uvx")
        if not uvx_path:
            self._alert("未找到 uvx，请确认已安装 uvx 并加入 PATH")
            return
        try:
            subprocess.Popen([uvx_path, "labelme"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as exc:
            self._alert(f"启动失败：{exc}")

    def on_progress_changed(self, value: int):
        if value < 0:
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(value)

    def on_status_changed(self, text: str):
        self.status_label.setText(text)

    def on_finished_ok(self, count: int):
        self.convert_btn.setEnabled(True)
        self.status_label.setText(f"转换完成，共 {count} 帧")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)

    def on_failed(self, message: str):
        self.convert_btn.setEnabled(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self._alert(message)

    def _default_output_dir(self, video_path: str) -> str:
        folder = os.path.dirname(video_path)
        filename = os.path.basename(video_path)
        name, _ = os.path.splitext(filename)
        return os.path.join(folder, name)

    def _alert(self, message: str):
        QMessageBox.warning(self, "提示", message)


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(860, 220)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
