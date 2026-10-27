"""Structure checks + Code-node logic in Node.js (no paid API calls)."""
import json, shutil, subprocess, unittest
from pathlib import Path
import generate_workflow as gw

HERE = Path(__file__).parent
WF = gw.workflow
NODE = shutil.which("node")


def run_js(code, items, refs=None):
    harness = f"""
const items = {json.dumps(items)}; const refs = {json.dumps(refs or {})};
const $input = {{ all: () => items, first: () => items[0] }};
const $ = (n) => ({{ all: () => refs[n] || [], first: () => (refs[n] || [])[0] }});
(async function () {{ {code} }})().then(r => console.log(JSON.stringify(r))).catch(e => {{ console.log(JSON.stringify({{ error: e.message }})); }});
"""
    res = subprocess.run([NODE, "-e", harness], capture_output=True, text=True, encoding="utf-8", timeout=30)
    if res.returncode:
        raise AssertionError(res.stderr)
    return json.loads(res.stdout)


def gem(obj):
    return [{"json": {"candidates": [{"content": {"parts": [{"text": json.dumps(obj)}]}}]}}]


class TestStructure(unittest.TestCase):
    def test_file_matches_generator(self):
        self.assertEqual(json.loads((HERE / "Viral_Shorts_Generator.json").read_text(encoding="utf-8")), json.loads(json.dumps(WF)))

    def test_connections(self):
        names = {n["name"] for n in WF["nodes"]}
        for src, out in WF["connections"].items():
            self.assertIn(src, names)
            for br in out["main"]:
                for c in br:
                    self.assertIn(c["node"], names)

    def test_poll_loops_back(self):
        outs = WF["connections"]["Video Ready?"]["main"]
        self.assertEqual([o[0]["node"] for o in outs], ["Download Video", "Wait 30s", "Video Failed"])

    def test_no_secrets(self):
        self.assertNotRegex((HERE / "Viral_Shorts_Generator.json").read_text(encoding="utf-8"), r"AIza[0-9A-Za-z_\-]{30,}|\b\d{17,20}\b|\$env\.")


@unittest.skipUnless(NODE, "Node.js not installed")
class TestLogic(unittest.TestCase):
    def brief(self, body):
        return run_js(gw.BRIEF_JS, [{"json": {"body": body}}])[0]["json"]

    def test_dry_run_is_default(self):
        self.assertTrue(self.brief({})["dryRun"])
        self.assertTrue(self.brief({"dryRun": "yes"})["dryRun"])
        self.assertFalse(self.brief({"dryRun": False})["dryRun"])

    def test_seconds_clamped(self):
        self.assertEqual(self.brief({"seconds": 60})["seconds"], 10)
        self.assertEqual(self.brief({"seconds": "x"})["seconds"], 8)

    def test_parse_concept(self):
        brief = self.brief({"topic": "Desk setup", "dryRun": False})
        out = run_js(gw.PARSE_JS, gem({"title": "Your Desk Is Costing You Hours!", "hook": "Stop doing this", "video_prompt": "Slow push-in on a tidy desk",
                                       "caption": "Which one do you do?", "hashtags": ["#productivity", "desk setup", "x"]}),
                     {"Brief": [{"json": brief}]})[0]["json"]
        self.assertEqual(out["fileName"], "your-desk-is-costing-you-hours.mp4")
        self.assertIn("#productivity #desksetup #x", out["caption"])
        self.assertEqual(out["omniRequest"]["response_format"]["aspect_ratio"], "9:16")
        self.assertEqual(out["omniRequest"]["model"], gw.VIDEO_MODEL)
        self.assertIn("no logos", out["videoPrompt"])
        self.assertFalse(out["dryRun"])

    def test_parse_concept_without_prompt_fails(self):
        out = run_js(gw.PARSE_JS, gem({"title": "x"}), {"Brief": [{"json": self.brief({})}]})
        self.assertIn("no video_prompt", out["error"])

    def test_video_job(self):
        r = {"steps": [{"content": [{"type": "text"}, {"type": "video", "uri": f"{gw.API}/files/abc123:download?alt=media"}]}]}
        self.assertEqual(run_js(gw.VIDEO_JOB_JS, [{"json": r}])[0]["json"]["fileId"], "abc123")
        self.assertIn("no video file", run_js(gw.VIDEO_JOB_JS, [{"json": {"error": {"code": 402}}}])["error"])

    def test_review_message(self):
        out = run_js(gw.REVIEW_JS, [{"json": {"id": "f1"}}], {"Parse Concept": [{"json": {"title": "T", "hook": "H", "caption": "C"}}]})[0]["json"]
        self.assertIn("https://drive.google.com/file/d/f1/view", out["content"])
        self.assertLessEqual(len(out["content"]), 1990)


if __name__ == "__main__":
    unittest.main(verbosity=1)
