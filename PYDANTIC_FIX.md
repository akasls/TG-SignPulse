# Pydantic V1 兼容性修复

## 问题描述
应用启动失败，报错 `ImportError: cannot import name 'field_validator' from 'pydantic'`。
原因是在 `pyproject.toml` 中锁定了 `pydantic<2`（V1版本），但代码中使用了 Pydantic V2 的新特性 `field_validator` 和 `model_dump()`。

## 修复内容
修改 `backend/api/routes/sign_tasks.py`：

1. **导入修改**：
   ```python
   # Old (V2)
   from pydantic import BaseModel, Field, field_validator
   
   # New (V1)
   from pydantic import BaseModel, Field, validator
   ```

2. **验证器修改**：
   ```python
   # Old (V2)
   @field_validator('name')
   
   # New (V1)
   @validator('name')
   ```

3. **数据导出修改**：
   ```python
   # Old (V2)
   chat.model_dump()
   
   # New (V1)
   chat.dict()
   ```

## 影响评估
此次修改仅涉及代码兼容性降级，逻辑功能保持不变。Pydantic V1 的 `validator` 和 `dict` 方法足以满足当前的验证和序列化需求。
