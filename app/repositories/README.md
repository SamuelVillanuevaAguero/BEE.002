# Repository Pattern - Job Management

## Overview

Este proyecto implementa el **Repository Pattern** para la gestión de jobs y sus historiales de ejecución. El patrón Repository es un patrón de diseño que actúa como una **abstracción de la capa de acceso a datos (DAL)**.

## Beneficios del Repository Pattern

✅ **Separación de responsabilidades**: La lógica de acceso a datos está aislada de la lógica de negocio  
✅ **Testabilidad**: Fácil crear mocks del repositorio para tests unitarios  
✅ **Mantenibilidad**: Cambios en la BD requieren actualizar solo el repositorio  
✅ **Reusabilidad**: Los métodos de consulta pueden reutilizarse en múltiples servicios  
✅ **Consistencia**: Operaciones CRUD uniformes en todos los repositorios  

## Estructura

```
app/repositories/
├── __init__.py                 # Exporta los repositorios
├── base_repository.py          # Clase base genérica con CRUD básico
└── job_repository.py           # Repositorios especializados para Job y JobExecution
```

## Componentes

### 1. BaseRepository (Clase Base Genérica)

Proporciona operaciones CRUD genéricas para cualquier modelo SQLAlchemy:

```python
from app.repositories import BaseRepository

class BaseRepository(Generic[T]):
    def create(self, obj_in: dict) -> T              # Crear
    def get_by_id(self, id: Any) -> Optional[T]      # Obtener por ID
    def get_all(self) -> List[T]                      # Obtener todos
    def update(self, id: Any, obj_in: dict) -> T    # Actualizar
    def delete(self, id: Any) -> bool                 # Eliminar
    def exists(self, id: Any) -> bool                 # Verificar existencia
    def flush(self) -> None                           # Flush (sin commit)
    def commit(self) -> None                          # Commit
    def refresh(self, obj: T) -> None                 # Refresh
```

### 2. JobRepository (Repositorio Especializado para Job)

Extiende `BaseRepository[Job]` con métodos específicos:

```python
from app.repositories import JobRepository

repo = JobRepository(db)

# Métodos específicos
repo.get_by_status(status: JobStatus)           # Obtener jobs por estado
repo.list_all(status: Optional[JobStatus])      # Listar todos (con filtro opcional)
repo.get_by_name(name: str)                     # Obtener por nombre
repo.get_active_jobs()                          # Obtener jobs activos
repo.get_paused_jobs()                          # Obtener jobs pausados
repo.update_status(job_id, status)              # Actualizar estado
repo.update_next_run_time(job_id, time)         # Actualizar próx ejecución
repo.update_trigger_args(job_id, args)          # Actualizar args del trigger
repo.update_job_kwargs(job_id, kwargs)          # Actualizar job kwargs
repo.update_job_details(job_id, name, desc)     # Actualizar nombre/descripción
repo.count_jobs()                               # Contar total de jobs
repo.count_by_status(status)                    # Contar por estado
```

### 3. JobExecutionRepository (Repositorio para Histórico)

Extiende `BaseRepository[JobExecution]` para historiales:

```python
from app.repositories.job_repository import JobExecutionRepository

exec_repo = JobExecutionRepository(db)

# Métodos específicos
exec_repo.get_by_job_id(job_id)                           # Todas las ejecuciones
exec_repo.get_by_job_id_paginated(job_id, page, size)    # Con paginación
exec_repo.get_executions_paginated(job_id, page, size)   # Global con filtro
exec_repo.get_recent_executions(job_id, limit)           # Últimas N ejecuciones
exec_repo.get_failed_executions(job_id)                  # Solo fallos
exec_repo.get_successful_executions(job_id)              # Solo éxitos
exec_repo.count_by_status(job_id, status)                # Contar por estado
exec_repo.get_job_execution_stats(job_id)                # Estadísticas completas
```

## Uso en Services

### Ejemplo: Crear un Job

**Antes (Sin Repository):**
```python
db_job = Job(
    id=job_id,
    name=payload.name,
    description=payload.description,
    task_path=payload.task_path,
    trigger_type=payload.trigger_type,
    trigger_args=payload.trigger_args,
    job_kwargs=payload.job_kwargs,
    status=JobStatus.active,
    next_run_time=aps_job.next_run_time,
)
db.add(db_job)
db.commit()
db.refresh(db_job)
```

**Después (Con Repository):**
```python
repo = JobRepository(db)
db_job = repo.create({
    "id": job_id,
    "name": payload.name,
    "description": payload.description,
    "task_path": payload.task_path,
    "trigger_type": payload.trigger_type,
    "trigger_args": payload.trigger_args,
    "job_kwargs": payload.job_kwargs,
    "status": JobStatus.active,
    "next_run_time": aps_job.next_run_time,
})
```

### Ejemplo: Obtener y Actualizar Job

```python
repo = JobRepository(db)

# Obtener
job = repo.get_by_id(job_id)

# Actualizar estado
job = repo.update_status(job_id, JobStatus.paused)

# Actualizar múltiples campos
job = repo.update_job_details(job_id, name="New Name", description="New Desc")
```

### Ejemplo: Obtener Histórico con Paginación

```python
exec_repo = JobExecutionRepository(db)

# Obtener con paginación
result = exec_repo.get_executions_paginated(
    job_id="abc123",
    page=1,
    page_size=20
)

# Resultado
{
    "total": 100,
    "page": 1,
    "page_size": 20,
    "items": [JobExecution(...), ...]
}
```

### Ejemplo: Estadísticas de Ejecución

```python
exec_repo = JobExecutionRepository(db)

stats = exec_repo.get_job_execution_stats("abc123")

# Resultado
{
    "total": 50,
    "success": 48,
    "failure": 2,
    "running": 0,
    "success_rate": 96.0
}
```

## Flujo de Trabajo con Repository

```
Controller/Route
    ↓
Service Layer (job_service.py)
    ↓
Repository Layer ← Database
    ↓
Model/Entity
```

## Ventajas Clave

| Aspecto | Sin Repository | Con Repository |
|--------|---|---|
| **Queries directas en Service** | Sí (Acopladas) | No (Aisladas) |
| **Fácil cambiar BD** | Difícil | Fácil |
| **Testear Service** | Requiere mock de Session | Mock simple del Repo |
| **Lógica de queries** | Dispersa | Centralizada |
| **Reutilización** | Baja | Alta |

## Testing

Con el Repository Pattern, los tests son más simples:

```python
from unittest.mock import Mock
from app.repositories import JobRepository

def test_get_active_jobs():
    # Mock del repositorio
    mock_repo = Mock(spec=JobRepository)
    mock_repo.get_active_jobs.return_value = [job1, job2]
    
    # Test del servicio
    result = my_service.list_active_jobs(mock_repo)
    assert len(result) == 2
```

## Extensión del Patrón

Para crear un nuevo repositorio, hereda de `BaseRepository`:

```python
from app.repositories.base_repository import BaseRepository
from app.models.client import Client

class ClientRepository(BaseRepository[Client]):
    def __init__(self, db: Session):
        super().__init__(db, Client)
    
    # Métodos específicos para Client
    def get_by_email(self, email: str) -> Optional[Client]:
        stmt = select(Client).where(Client.email == email)
        return self.db.execute(stmt).scalars().first()
```

## Referencias

- [Repository Pattern - Microsoft Docs](https://docs.microsoft.com/en-us/dotnet/architecture/microservices/microservice-ddd-cqrs-patterns/infrastructure-persistence-layer-design)
- [SOLID Principles](https://en.wikipedia.org/wiki/SOLID)
- [SQLAlchemy ORM](https://docs.sqlalchemy.org/en/20/orm/)
