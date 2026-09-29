"""공식 Faster R-CNN v2 RSNA 적응: dataset, model, 학습 loop 보조, checkpoint 원자 저장/재개, 평가.
natten_py310 환경(torch 2.6.0+cu124, torchvision 0.21.0+cu124)에서만 실행한다.

iter_033의 results/iter_033/detector_lib.py를 원본으로 하고, iter_034에서 다음을 추가했다 (원본 sha256
d562f8b2059c24678a7bafc8798aa541b47a6a72c2e582aed96346c38d53a394):
- RSNADetDataset.__getitem__이 실제 적용한 flip 여부를 target["flip"]으로 반환한다 (재개 로그 검증용).
그 외 dataset/model/optimizer/scheduler/rng/checkpoint 유틸리티 로직은 원본과 동일하다.
iter_035: flip_p·min_size·max_size를 인자로 노출했다(기본값 0.5/800/1333은 기존 동작·torchvision 기본값과 동일).
"""
import hashlib
import json
import os
import random
import sys

import numpy as np
import torch
from PIL import Image
from torch.utils.data import Dataset

sys.path.insert(0, "/SSD1_1TB/home/milab/daniel/08_medgemma/research")
from rsna_diag import geometry as G

BASE = "/SSD1_1TB/home/milab/daniel/08_medgemma/research"
IT010 = f"{BASE}/results/iter_010/manifests"


def load_gt_infer():
    gt = json.load(open(f"{IT010}/gt_manifest.json"))
    infer = {}
    with open(f"{IT010}/infer_manifest.jsonl") as f:
        for line in f:
            r = json.loads(line)
            infer[r["id"]] = r
    return gt, infer


class RSNADetDataset(Dataset):
    """원본 uint8 영상(RGB 복제, 값 보존) + pixel xyxy GT box(opacity=label1). horizontal flip만 augmentation."""

    def __init__(self, ids, gt, infer, train_aug=False, seed=0, flip_p=0.5):
        self.ids = list(ids)
        self.gt = gt
        self.infer = infer
        self.train_aug = train_aug
        self.flip_p = flip_p
        self.rng = random.Random(seed)

    def __len__(self):
        return len(self.ids)

    def set_epoch_rng(self, seed):
        self.rng = random.Random(seed)

    def __getitem__(self, idx):
        pid = self.ids[idx]
        rec = self.infer[pid]
        path = f"{BASE}/{rec['image']}"
        arr = np.array(Image.open(path))
        rgb = G.to_uint8_rgb_preserving(arr)
        h, w = rgb.shape[:2]
        g = self.gt[pid]
        boxes = [b["xyxy_px"] for b in g["boxes"]]
        do_flip = self.train_aug and self.rng.random() < self.flip_p
        if do_flip:
            rgb = np.ascontiguousarray(rgb[:, ::-1, :])
            boxes = [[w - x1, y0, w - x0, y1] for x0, y0, x1, y1 in boxes]
        img = torch.from_numpy(rgb).permute(2, 0, 1).float() / 255.0
        if boxes:
            boxes_t = torch.tensor(boxes, dtype=torch.float32)
            labels_t = torch.ones((len(boxes),), dtype=torch.int64)
        else:
            boxes_t = torch.zeros((0, 4), dtype=torch.float32)
            labels_t = torch.zeros((0,), dtype=torch.int64)
        target = {"boxes": boxes_t, "labels": labels_t, "image_id": pid, "flip": bool(do_flip)}
        return img, target, (h, w)


def collate_fn(batch):
    imgs = [b[0] for b in batch]
    targets = [b[1] for b in batch]
    dims = [b[2] for b in batch]
    return imgs, targets, dims


def build_model(num_classes=2, trainable_backbone_layers=5, min_size=800, max_size=1333):
    from torchvision.models.detection import fasterrcnn_resnet50_fpn_v2, FasterRCNN_ResNet50_FPN_V2_Weights
    from torchvision.models.detection.faster_rcnn import FastRCNNPredictor

    weights = FasterRCNN_ResNet50_FPN_V2_Weights.COCO_V1
    model = fasterrcnn_resnet50_fpn_v2(weights=weights, trainable_backbone_layers=trainable_backbone_layers,
                                       box_score_thresh=0.001, box_nms_thresh=0.5, box_detections_per_img=100,
                                       min_size=min_size, max_size=max_size)
    in_features = model.roi_heads.box_predictor.cls_score.in_features
    model.roi_heads.box_predictor = FastRCNNPredictor(in_features, num_classes)
    return model


def freeze_bn_running_stats(model):
    """BatchNorm running statistics 고정, affine parameter는 학습 유지. train() 호출 뒤 매번 강제한다."""
    for m in model.modules():
        if isinstance(m, torch.nn.modules.batchnorm._BatchNorm):
            m.eval()
            if m.weight is not None:
                m.weight.requires_grad_(True)
            if m.bias is not None:
                m.bias.requires_grad_(True)


def set_train_mode(model):
    model.train()
    freeze_bn_running_stats(model)


def build_optimizer(model, lr=0.005, momentum=0.9, weight_decay=1e-4):
    params = [p for p in model.parameters() if p.requires_grad]
    return torch.optim.SGD(params, lr=lr, momentum=momentum, weight_decay=weight_decay)


def linear_warmup_then_multistep(optimizer, warmup_updates, milestones_updates, gamma=0.1):
    def lr_lambda(step):
        if step < warmup_updates:
            return (step + 1) / warmup_updates
        factor = 1.0
        for m in milestones_updates:
            if step >= m:
                factor *= gamma
        return factor
    return torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda)


def full_rng_state():
    return {
        "python": random.getstate(),
        "numpy": np.random.get_state(),
        "torch_cpu": torch.get_rng_state(),
        "torch_cuda": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None,
    }


def restore_rng_state(state, cuda_map=None):
    """cuda_map=(저장 당시 학습 장치 index, 현재 학습 장치 index): 저장 process와 현재 process가 보는 GPU 수가
    다를 수 있으므로 학습에 쓰인 장치의 CUDA generator만 옮긴다. None이면 기존처럼 전체 장치를 복원한다."""
    random.setstate(state["python"])
    np.random.set_state(state["numpy"])
    torch.set_rng_state(state["torch_cpu"])
    if state["torch_cuda"] is not None and torch.cuda.is_available():
        if cuda_map is None:
            torch.cuda.set_rng_state_all(state["torch_cuda"])
        else:
            torch.cuda.set_rng_state(state["torch_cuda"][cuda_map[0]], device=cuda_map[1])


def optimizer_state_to_device(optimizer, device):
    for state in optimizer.state.values():
        for k, v in state.items():
            if torch.is_tensor(v):
                state[k] = v.to(device)


def atomic_save(obj, path):
    tmp = path + ".tmp"
    torch.save(obj, tmp)
    os.replace(tmp, path)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def protocol_digest(paths):
    entries = {}
    for p in sorted(paths):
        entries[p] = sha256_file(p)
    blob = json.dumps(entries, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest(), entries


@torch.no_grad()
def run_inference(model, device, ids, gt, infer, batch_size=4):
    """returns {id: {'boxes_xyxy_px':..., 'scores':..., 'labels':..., 'img_hw':(h,w)}}"""
    model.eval()
    ds = RSNADetDataset(ids, gt, infer, train_aug=False)
    out = {}
    i = 0
    while i < len(ds):
        batch_ids = ds.ids[i:i + batch_size]
        imgs = []
        dims = []
        for pid in batch_ids:
            img, _, hw = ds[ds.ids.index(pid)]
            imgs.append(img.to(device))
            dims.append(hw)
        preds = model(imgs)
        for pid, pr, hw in zip(batch_ids, preds, dims):
            out[pid] = {
                "boxes_xyxy_px": pr["boxes"].detach().cpu().numpy().tolist(),
                "scores": pr["scores"].detach().cpu().numpy().tolist(),
                "labels": pr["labels"].detach().cpu().numpy().tolist(),
                "img_hw": list(hw),
            }
        i += batch_size
    return out


def preds_to_norm_yxyx(raw_preds, gt, threshold):
    """detector 원시 pred(pixel xyxy, score, label) -> sft_eval 호환 {'status':..., 'boxes':[[y0,x0,y1,x1],...]} (0-1000 norm).
    label==1(opacity)만 인정, score>=threshold만 유지."""
    out = {}
    for pid, r in raw_preds.items():
        h, w = r["img_hw"]
        top, left, side = G.pad_offsets(h, w)
        boxes = []
        for box, score, label in zip(r["boxes_xyxy_px"], r["scores"], r["labels"]):
            if label != 1 or score < threshold:
                continue
            boxes.append(G.canvas_to_norm(box, top, left, side))
        out[pid] = {"status": "valid_nonempty" if boxes else "valid_empty", "boxes": boxes}
    return out
