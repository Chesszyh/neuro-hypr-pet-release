import tempfile
import unittest
from pathlib import Path

from neuro_hypr_pet.service import render_shimeji_user_service, write_shimeji_user_service, write_manager_desktop_entry


class ShimejiServiceTest(unittest.TestCase):
    def test_render_shimeji_user_service_uses_absolute_paths_and_low_load_defaults(self) -> None:
        text = render_shimeji_user_service(
            repo_root=Path("/repo/neuro-hypr-pet"),
            collection=Path("/repo/neuro-hypr-pet/refs/The-Neuroling-Collection"),
            image_set="Neuron",
            monitor="eDP-1",
            fps=15,
            python=Path("/usr/bin/python3"),
        )

        self.assertIn("Description=Neuro Hypr Pet sprite-bounded Shimeji runtime", text)
        self.assertIn("Environment=GDK_BACKEND=wayland", text)
        self.assertIn("Environment=GSK_RENDERER=cairo", text)
        self.assertIn("WorkingDirectory=/repo/neuro-hypr-pet", text)
        self.assertIn("/usr/bin/python3 /repo/neuro-hypr-pet/tools/neuro_hypr_shimeji.py", text)
        self.assertIn("PartOf=graphical-session.target", text)
        self.assertIn("After=graphical-session.target", text)
        self.assertIn("ConditionEnvironment=WAYLAND_DISPLAY", text)
        self.assertIn(
            "ConditionPathExists=/repo/neuro-hypr-pet/refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml",
            text,
        )
        self.assertIn("--collection /repo/neuro-hypr-pet/refs/The-Neuroling-Collection", text)
        self.assertIn("--image-set Neuron", text)
        self.assertIn("--monitor eDP-1", text)
        self.assertIn("--fps 15", text)
        self.assertNotIn("--move-active-window", text)
        self.assertIn("WantedBy=graphical-session.target", text)
        self.assertNotIn("WantedBy=default.target", text)
        self.assertNotIn("Wants=graphical-session.target", text)

    def test_render_shimeji_user_service_can_enable_active_window_moving_explicitly(self) -> None:
        text = render_shimeji_user_service(
            repo_root=Path("/repo/neuro-hypr-pet"),
            collection=Path("/repo/neuro-hypr-pet/refs/The-Neuroling-Collection"),
            image_set="Neuron",
            monitor="eDP-1",
            fps=15,
            python=Path("/usr/bin/python3"),
            move_active_window=True,
        )

        self.assertIn("--move-active-window", text)

    def test_write_shimeji_user_service_writes_rendered_service(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = Path(tmp) / "neuro-hypr-pet-shimeji.service"

            write_shimeji_user_service(
                service,
                repo_root=Path("/repo/neuro-hypr-pet"),
                collection=Path("/repo/neuro-hypr-pet/refs/The-Neuroling-Collection"),
                image_set="Neuron",
                monitor="eDP-1",
                fps=15,
                python=Path("/usr/bin/python3"),
            )

            text = service.read_text(encoding="utf-8")

        self.assertIn("ExecStart=/usr/bin/python3 /repo/neuro-hypr-pet/tools/neuro_hypr_shimeji.py", text)

    def test_service_can_use_remembered_selection(self) -> None:
        text = render_shimeji_user_service(repo_root=Path("/repo"), collection=Path("/assets"),
                                           image_set=None, monitor="auto", fps=25, python=Path("/usr/bin/python3"))
        self.assertNotIn("--image-set", text)
        self.assertIn("ConditionPathExists=/assets/img", text)

    def test_launcher_opens_manager(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "applications/pet.desktop"
            write_manager_desktop_entry(path, repo_root=Path("/repo/pet"), collection=Path("/assets/pets"), python=Path("/usr/bin/python3"))
            text = path.read_text()
        self.assertIn('"/repo/pet/tools/neuro_hypr_shimeji.py"', text)
        self.assertIn('"--manage"', text)
        self.assertIn("Terminal=false", text)


if __name__ == "__main__":
    unittest.main()
