# 运行任务报错修复

## 问题描述
点击“运行”任务时报错：
```
RuntimeError: no validator found for <class 'functools.cached_property'>
```

## 原因
这是由于 Pydantic V1（为了兼容性而降级）与 Python 的 `cached_property` 装饰器存在冲突。Pydantic 错误地试图验证这个属性，而不是忽略它。

## 修复方案
修改了 `tg_signer/config.py`，配置 Pydantic 忽略 `cached_property`：
```python
    class Config:
        keep_untouched = (cached_property,)
        arbitrary_types_allowed = True
```

## 警告说明
您看到的 `TgCrypto is missing!` 仅仅是一个性能提示，**不是错误**。它不会阻止程序运行，您可以忽略它。

## 下一步
1. **拉取代码**：
   ```bash
   git pull
   ```
2. **重建容器**（因为这涉及到底层库代码的修改）：
   ```bash
   docker-compose up -d --build
   ```
3. **再次点击运行**。

这次应该可以成功运行了！
