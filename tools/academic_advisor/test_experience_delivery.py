"""Guard the response transport's configured presentation overhead."""
import inspect, unittest
from stream_chat import install_stream
class ExperienceDeliveryTests(unittest.TestCase):
    def test_delivery_pause_budget(self):
        params=inspect.signature(install_stream).parameters
        self.assertLessEqual(44*params['interval'].default,0.4)
        self.assertLessEqual(params['heartbeat'].default,1.0)
if __name__=='__main__':unittest.main()
