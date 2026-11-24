from unittest.mock import patch
import pytest
from src.lora import device_policy as d

@pytest.mark.parametrize("requested,nvidia,expected", [("auto",True,"cuda"),("auto",False,"cpu"),("cpu",True,"cpu"),("cuda",False,"cuda")])
def test_device_selection(requested,nvidia,expected):
    with patch.object(d,"nvidia_detected",return_value=nvidia):
        assert d.choose_device(requested)==expected

@pytest.mark.parametrize("available,allowed", [(8,False),(13,False),(14,True),(24,True)])
def test_memory_gate(available,allowed):
    with patch.object(d,"effective_available_ram",return_value=available*d.GIB):
        if allowed:
            assert d.require_cpu_memory()==available*d.GIB
        else:
            with pytest.raises(RuntimeError,match="CPU_RAM_INSUFFICIENT"):
                d.require_cpu_memory()

from scripts import bootstrap_chronoreg as b

@pytest.mark.parametrize("device,torch_build", [("cpu","cpu"),("cuda","cu126")])
def test_dependency_mode(device,torch_build):
    installed=dict(b.PACKAGES)
    installed["torch"]="old"
    calls=[]
    def fake_pip(*args): calls.append(args)
    with patch.object(b,"version",side_effect=installed.get), patch.object(b,"pip",side_effect=fake_pip), patch.object(b,"require_cpu_memory",return_value=24*d.GIB), patch.object(b.shutil,"which",return_value="/usr/bin/gcc"), patch.object(b.subprocess,"run") as runner:
        b.ensure_deps(device)
    assert calls[0]==("torch==2.7.1","--index-url","https://download.pytorch.org/whl/"+torch_build)
    code=runner.call_args.args[0][-1]
    if device=="cpu":
        assert len(calls)==1
        assert "import bitsandbytes" not in code
        assert runner.call_args.kwargs["env"]["CUDA_VISIBLE_DEVICES"]==""
    else:
        assert calls[1]==("bitsandbytes==0.48.2",)
        assert "import bitsandbytes" in code
        assert runner.call_args.kwargs["env"]["CUDA_VISIBLE_DEVICES"]=="0"

def test_cpu_does_not_modify_cuda_environment():
    with patch.object(b,"version",side_effect=lambda n: "0.48.2" if n=="bitsandbytes" else b.PACKAGES.get(n)), patch.object(b,"require_cpu_memory",return_value=24*d.GIB), patch.object(b,"pip") as install:
        with pytest.raises(RuntimeError,match="clean CPU environment"):
            b.ensure_deps("cpu")
        install.assert_not_called()
