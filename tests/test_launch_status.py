import unittest
from flyterm.launch_status import load_instance,public_status
class LaunchStatusTests(unittest.TestCase):
    def test_instance_file_is_unpublished(self):
        cfg=load_instance()
        self.assertFalse(cfg.get("published"))
        self.assertFalse(cfg.get("officialProduct"))
        self.assertFalse(cfg.get("token"))
    def test_public_status_without_published_instance(self):
        out=public_status()
        self.assertFalse(out["ok"])
        self.assertFalse(out["published"])
        self.assertFalse(out["officialProduct"])
if __name__=="__main__":unittest.main()
