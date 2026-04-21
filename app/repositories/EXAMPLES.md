"""
app/repositories/EXAMPLES.md
Ejemplos prácticos de uso del Repository Pattern para Jobs
"""

# EJEMPLOS DE USO DEL REPOSITORY PATTERN

## 1. Crear un Job

```python
from sqlalchemy.orm import Session
from app.repositories import JobRepository
from app.models.job import JobStatus, TriggerType

async def create_job_example(db: Session):
    repo = JobRepository(db)
    
    job = repo.create({
        "id": "job-123",
        "name": "Mi Job",
        "description": "Un job de ejemplo",
        "task_path": "app.tasks.my_module:my_function",
        "trigger_type": TriggerType.interval,
        "trigger_args": {"minutes": 30},
        "job_kwargs": {"param1": "value1"},
        "status": JobStatus.active,
        "next_run_time": datetime.now(timezone.utc),
    })
    
    return job
```

## 2. Obtener y Listar Jobs

```python
from app.repositories import JobRepository
from app.models.job import JobStatus

async def list_jobs_example(db: Session):
    repo = JobRepository(db)
    
    # Obtener un job específico
    job = repo.get_by_id("job-123")
    
    # Listar todos los jobs
    all_jobs = repo.list_all()
    
    # Listar solo jobs activos
    active_jobs = repo.get_active_jobs()
    
    # Listar jobs pausados
    paused_jobs = repo.get_paused_jobs()
    
    # Obtener por nombre
    job_by_name = repo.get_by_name("Mi Job")
    
    return {"all": all_jobs, "active": active_jobs, "paused": paused_jobs}
```

## 3. Actualizar Jobs

```python
async def update_job_example(db: Session):
    repo = JobRepository(db)
    
    # Actualizar solo el estado
    job = repo.update_status("job-123", JobStatus.paused)
    
    # Actualizar nombre y descripción
    job = repo.update_job_details(
        "job-123",
        name="Nuevo Nombre",
        description="Nueva descripción"
    )
    
    # Actualizar argumentos del trigger
    job = repo.update_trigger_args("job-123", {"minutes": 60})
    
    # Actualizar kwargs del job
    job = repo.update_job_kwargs("job-123", {"new_param": "new_value"})
    
    # Actualizar próxima ejecución
    next_run = datetime.now(timezone.utc) + timedelta(hours=1)
    job = repo.update_next_run_time("job-123", next_run)
    
    return job
```

## 4. Eliminar un Job

```python
async def delete_job_example(db: Session):
    repo = JobRepository(db)
    
    # Verificar si existe
    if repo.exists("job-123"):
        # Eliminar
        success = repo.delete("job-123")
        return {"deleted": success}
    
    return {"deleted": False, "reason": "Job no encontrado"}
```

## 5. Contar Jobs

```python
async def count_jobs_example(db: Session):
    repo = JobRepository(db)
    
    # Total de jobs
    total = repo.count_jobs()
    
    # Contar por estado
    active_count = repo.count_by_status(JobStatus.active)
    paused_count = repo.count_by_status(JobStatus.paused)
    
    return {
        "total": total,
        "active": active_count,
        "paused": paused_count
    }
```

## 6. Obtener Histórico de Ejecuciones

```python
from app.repositories.job_repository import JobExecutionRepository

async def get_executions_example(db: Session):
    exec_repo = JobExecutionRepository(db)
    
    # Obtener todas las ejecuciones de un job
    all_executions = exec_repo.get_by_job_id("job-123")
    
    # Con paginación
    result = exec_repo.get_by_job_id_paginated(
        job_id="job-123",
        page=1,
        page_size=20
    )
    # Resultado: {"total": 100, "page": 1, "page_size": 20, "items": [...]}
    
    # Últimas 10 ejecuciones
    recent = exec_repo.get_recent_executions("job-123", limit=10)
    
    # Solo ejecuciones exitosas
    successful = exec_repo.get_successful_executions("job-123")
    
    # Solo ejecuciones fallidas
    failed = exec_repo.get_failed_executions("job-123")
    
    return {
        "all": all_executions,
        "recent": recent,
        "successful": successful,
        "failed": failed
    }
```

## 7. Obtener Estadísticas de un Job

```python
async def get_stats_example(db: Session):
    exec_repo = JobExecutionRepository(db)
    
    # Obtener estadísticas completas
    stats = exec_repo.get_job_execution_stats("job-123")
    
    """
    Resultado:
    {
        "total": 50,
        "success": 48,
        "failure": 2,
        "running": 0,
        "success_rate": 96.0
    }
    """
    
    # Contar por estado específico
    success_count = exec_repo.count_by_status("job-123", ExecutionStatus.success)
    failure_count = exec_repo.count_by_status("job-123", ExecutionStatus.failure)
    
    return {"stats": stats, "success": success_count, "failure": failure_count}
```

## 8. Operaciones en Transacciones

```python
async def transaction_example(db: Session):
    repo = JobRepository(db)
    
    # Crear y actualizar en la misma transacción
    try:
        # Crear nuevo job
        job = repo.create({
            "id": "job-456",
            "name": "Job Transaccional",
            # ... otros campos
        })
        
        # Realizar más operaciones
        job = repo.update_status("job-456", JobStatus.active)
        
        # Si todo es OK, commit automático en repo.commit()
        repo.commit()
        
        return {"status": "success", "job": job}
    except Exception as e:
        # En caso de error, rollback automático
        db.rollback()
        return {"status": "error", "message": str(e)}
```

## 9. Flush y Commit

```python
async def flush_commit_example(db: Session):
    repo = JobRepository(db)
    
    # Crear job
    job = repo.create({
        "id": "job-789",
        "name": "Flush Example",
        # ... otros campos
    })
    
    # Flush (envía INSERTs/UPDATEs a la BD pero no hace commit)
    repo.flush()
    
    # Aquí el job tiene ID pero no está committed
    # Si hay error, se puede rollback
    
    # Hacer commit para persistir los cambios
    repo.commit()
    
    # Refresh para obtener valores del servidor (default, triggers, etc)
    repo.refresh(job)
    
    return job
```

## 10. Integración con Service Layer

```python
from app.repositories import JobRepository
from app.models.job import JobStatus

class JobService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = JobRepository(db)
    
    async def activate_job(self, job_id: str):
        """Activar un job pausado"""
        job = self.repo.get_by_id(job_id)
        if not job:
            raise ValueError("Job no encontrado")
        
        if job.status == JobStatus.active:
            raise ValueError("El job ya está activo")
        
        # Aquí va la lógica de negocio (ej: registrar en scheduler)
        # scheduler.resume_job(job_id)
        
        # Actualizar en la BD usando el repositorio
        updated_job = self.repo.update_status(job_id, JobStatus.active)
        
        return updated_job
    
    async def get_job_summary(self, job_id: str):
        """Obtener resumen de un job"""
        from app.repositories.job_repository import JobExecutionRepository
        
        job = self.repo.get_by_id(job_id)
        if not job:
            raise ValueError("Job no encontrado")
        
        exec_repo = JobExecutionRepository(self.db)
        stats = exec_repo.get_job_execution_stats(job_id)
        
        return {
            "job": job,
            "stats": stats
        }
```

## 11. Búsquedas Avanzadas

```python
async def advanced_search_example(db: Session):
    repo = JobRepository(db)
    
    # Obtener todos los active jobs
    active = repo.get_by_status(JobStatus.active)
    
    # Filtro combinado: listar activos solamente
    active_list = repo.list_all(status=JobStatus.active)
    
    # Búsqueda por nombre
    job = repo.get_by_name("Mi Job Especial")
    
    # Contar estadísticas
    total = repo.count_jobs()
    active_count = repo.count_by_status(JobStatus.active)
    
    return {
        "active_jobs": active,
        "total_jobs": total,
        "active_count": active_count,
        "found_by_name": job
    }
```

## 12. Manejo de Errores

```python
async def error_handling_example(db: Session):
    repo = JobRepository(db)
    
    try:
        # Intentar obtener un job
        job = repo.get_by_id("job-no-existe")
        
        if job is None:
            print("Job no encontrado")
            return None
        
        # Intentar actualizar
        updated = repo.update_status("job-123", JobStatus.active)
        
    except Exception as e:
        print(f"Error en operación de repositorio: {e}")
        db.rollback()
        raise
    
    return updated
```

---

## Resumen de Métodos

### JobRepository
- `create(obj_in)` - Crear nuevo job
- `get_by_id(id)` - Obtener por ID
- `get_all()` - Obtener todos
- `update(id, obj_in)` - Actualizar genérico
- `delete(id)` - Eliminar
- `exists(id)` - Verificar existencia
- `list_all(status)` - Listar con filtro opcional
- `get_by_status(status)` - Obtener por estado
- `get_by_name(name)` - Obtener por nombre
- `get_active_jobs()` - Obtener activos
- `get_paused_jobs()` - Obtener pausados
- `update_status(id, status)` - Actualizar estado
- `update_next_run_time(id, time)` - Actualizar próx ejecución
- `update_trigger_args(id, args)` - Actualizar trigger
- `update_job_kwargs(id, kwargs)` - Actualizar kwargs
- `update_job_details(id, name, desc)` - Actualizar detalles
- `count_jobs()` - Contar total
- `count_by_status(status)` - Contar por estado

### JobExecutionRepository
- `get_by_job_id(job_id)` - Obtener ejecuciones
- `get_by_job_id_paginated(job_id, page, size)` - Con paginación
- `get_executions_paginated(job_id, page, size)` - Global con filtro
- `get_recent_executions(job_id, limit)` - Últimas N
- `get_failed_executions(job_id)` - Solo fallos
- `get_successful_executions(job_id)` - Solo éxitos
- `count_by_status(job_id, status)` - Contar por estado
- `get_job_execution_stats(job_id)` - Estadísticas completas
