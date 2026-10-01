"""iter_045 MedGrounder wrapper (격리 venv `results/environments/medgrounder_iter045`에서 실행).

공식 코드(a0aad98d, results/iter_045/external/MedGrounder)의 build_medgrounder / InferencePostProcessor / run_wbf /
dataloaders.dataset.build_transforms('val')를 그대로 호출한다. 공식 evaluation.py와 다른 점(의도된 차이):
  - checkpoint 부재·키 불일치는 fatal (random initialization fallback 금지, strict=True).
  - 공식 test loader를 만들지 않는다. 입력은 잠긴 D24/V96 manifest의 영상·문장뿐이다.
  - GT는 이 모듈에 들어오지 않는다 (평가는 mg45_eval.py).
좌표: 공식 val transform(LongestMaxSize(640)->PadIfNeeded(640,640,center)->Normalize)에 전체 영상 box [0,0,1,1]을 같이 통과시켜
실제 resize/padding affine(canvas 내 영상 영역 l,t,r,b)을 얻고, 모델 출력(canvas 정규화 cxcywh)을 원본 정규화 xyxy로 역변환한다 (추가 clipping 없음).
"""
import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
EXT = os.path.join(HERE, "results", "iter_045", "external")
MG_ROOT = os.path.join(EXT, "MedGrounder")
WEIGHTS = {"P": os.path.join(EXT, "weights", "medgrounder_pretrain_imagenome.pth"),
           "MS": os.path.join(EXT, "weights", "medgrounder_finetune_ms.pth")}
RUN_CFG = {"P": "conf/conf_pretrain_imagenome.yaml", "MS": "conf/conf_finetune_ms.yaml"}
THRESHOLDS = [0.2, 0.4, 0.6, 0.8]
WBF = {"run_wbf": True, "wbf_iou_threshold": 0.1, "skip_box_thr": 0.0, "run_nms": False}

os.environ.setdefault("HF_HUB_CACHE", os.path.join(EXT, "hf_cache"))
os.environ.setdefault("NO_ALBUMENTATIONS_UPDATE", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TORCH_HOME", os.path.join(EXT, "torch_home"))
sys.path.insert(0, MG_ROOT)


def file_sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 24), b""):
            h.update(b)
    return h.hexdigest()


def canon(o):
    return json.dumps(o, sort_keys=True, ensure_ascii=False, default=str)


def build_cfg(key):
    from omegaconf import OmegaConf
    cwd = os.getcwd()
    os.chdir(MG_ROOT)  # 공식 코드는 conf/ 상대경로
    try:
        base = OmegaConf.load("conf/base.yaml")
        ds = OmegaConf.load("conf/datasets.yaml")
        run = OmegaConf.load(RUN_CFG[key])
        cfg = OmegaConf.merge(ds, base, run)
    finally:
        os.chdir(cwd)
    cfg.resume = WEIGHTS[key]
    return cfg


def load_model(key, device):
    """returns (model, postprocessor_cls_threshold_cfg, cfg). strict load, 실패 시 예외."""
    import torch
    from model.medgrounder import build_medgrounder
    cfg = build_cfg(key)
    if not os.path.exists(cfg.resume):
        raise FileNotFoundError(cfg.resume)
    model, _crit, _post = build_medgrounder(cfg)
    ck = torch.load(cfg.resume, map_location="cpu", weights_only=True)
    sd = ck["model"] if isinstance(ck, dict) and "model" in ck else ck
    res = model.load_state_dict(sd, strict=True)  # 불일치면 RuntimeError
    model.to(device).eval()
    return model, cfg, {"missing": list(res.missing_keys), "unexpected": list(res.unexpected_keys),
                         "n_state_keys": len(sd), "ckpt_top_keys": list(ck.keys())[:5] if isinstance(ck, dict) else None}


def val_transform(imsize=640):
    from dataloaders.dataset import build_transforms
    return build_transforms("val", imsize)


def prepare(image_path, tf):
    """공식 dataset(GMPGPadChestDataset)과 같은 경로: PIL L -> RGB -> np -> val transform. returns (tensor[3,640,640], aff, u8_sha)."""
    import numpy as np
    from PIL import Image
    img = Image.open(image_path)
    if img.mode == "I;16":
        raise ValueError("uint16 입력은 이 wrapper 경로에서 지원하지 않는다 (manifest는 검증된 uint8 L PNG)")
    arr_l = np.array(img)
    u8_sha = hashlib.sha256(arr_l.tobytes()).hexdigest()
    img_np = np.array(img.convert("RGB"))
    out = tf(image=img_np, bboxes=np.array([[0.0, 0.0, 1.0, 1.0]], dtype=np.float32), bbox_labels=[1])
    if len(out["bboxes"]) != 1:
        raise RuntimeError("full-image box dropped by transform")
    l, t, r, b = [float(v) for v in out["bboxes"][0]]
    return out["image"], {"l": l, "t": t, "r": r, "b": b, "h": int(arr_l.shape[0]), "w": int(arr_l.shape[1])}, u8_sha


def canvas_cxcywh_to_orig_xyxy(boxes, aff):
    """canvas 정규화 cxcywh [N,4] -> 원본 정규화 xyxy list (clipping 없음)."""
    out = []
    W, H = aff["r"] - aff["l"], aff["b"] - aff["t"]
    for cx, cy, w, h in boxes:
        x0, y0, x1, y1 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
        out.append([(x0 - aff["l"]) / W, (y0 - aff["t"]) / H, (x1 - aff["l"]) / W, (y1 - aff["t"]) / H])
    return out


def postprocess(logits, boxes, thr):
    """공식 InferencePostProcessor(threshold) -> 공식 run_wbf. logits [B,5,2], boxes [B,5,4] (torch, cpu/gpu).
    returns list of {'boxes': cxcywh list, 'scores': list, 'pre_wbf_n': int}."""
    from model.medgrounder import InferencePostProcessor
    from utils.box_utils import run_wbf
    pp = InferencePostProcessor(threshold=thr)
    outs = pp({"pred_boxes": boxes, "pred_groundability": logits})
    det = outs["detections"]
    pre = [int(d["scores"].numel()) for d in det]
    det = run_wbf(det, iou_threshold=WBF["wbf_iou_threshold"], skip_box_threshold=WBF["skip_box_thr"])
    return [{"boxes": d["boxes"].cpu().tolist(), "scores": d["scores"].cpu().tolist(), "pre_wbf_n": n} for d, n in zip(det, pre)]


def forward(model, imgs, phrases, device):
    import torch
    from utils.misc import NestedTensor
    with torch.no_grad():
        x = torch.stack(imgs)
        # 공식 gmpg_collate_fn과 동일: mask는 전부 False (모델 내부 NestedTensor.from_tensor_list는 공식 코드에 없어 tensor를 직접 넘기면 실패)
        masks = torch.stack([torch.zeros_like(im[0], dtype=torch.bool) for im in imgs], dim=0)
        out = model(NestedTensor(x, masks).to(device), list(phrases))
    return out["pred_groundability"].float().cpu(), out["pred_boxes"].float().cpu()
