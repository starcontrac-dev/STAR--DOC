from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
import uuid
import logging

from app.auth import get_current_active_user
from app.models.user import User
from app.scheduler import scheduler, add_document_generation_job
from app.schemas.common import ScheduleCreate, JobRead

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Task Scheduler"])

@router.post("/schedule/", response_model=JobRead, status_code=status.HTTP_201_CREATED)
async def create_scheduled_job(
    schedule_data: ScheduleCreate,
    current_user: User = Depends(get_current_active_user)
):
    username = current_user.username
    job_id = schedule_data.job_id or f"{username}_{uuid.uuid4()}"

    if not job_id.startswith(username):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="El ID del trabajo debe comenzar con el nombre de usuario.")

    try:
        job = add_document_generation_job(
            job_id=job_id,
            template_name=schedule_data.template_name,
            context=schedule_data.context,
            output_format=schedule_data.output_format,
            user_id=username,
            cron_expression=schedule_data.cron_expression,
            google_doc_id=schedule_data.google_doc_id
        )
        if job:
            return JobRead(
                id=job.id,
                name=job.name,
                trigger=str(job.trigger),
                next_run_time=job.next_run_time
            )
        else:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No se pudo crear la tarea programada.")
    except Exception as e:
        logger.error(f"Error al crear la tarea programada: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.get("/schedule/", response_model=List[JobRead])
async def get_scheduled_jobs(current_user: User = Depends(get_current_active_user)):
    username = current_user.username
    jobs = scheduler.get_jobs()
    
    # Filter jobs for user
    user_jobs = []
    for job in jobs:
        # Check if job ID starts with username (our convention)
        if str(job.id).startswith(username):
             user_jobs.append(JobRead(
                id=job.id,
                name=job.name,
                trigger=str(job.trigger),
                next_run_time=job.next_run_time
            ))
    return user_jobs

@router.delete("/schedule/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scheduled_job(job_id: str, current_user: User = Depends(get_current_active_user)):
    username = current_user.username
    
    if not job_id.startswith(username):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tiene permiso para eliminar esta tarea.")
    
    try:
        scheduler.remove_job(job_id)
        logger.info(f"Tarea '{job_id}' eliminada por '{username}'.")
    except Exception as e:
        logger.error(f"Error al eliminar la tarea '{job_id}': {e}")
        # If job not found, usually apscheduler raises JobLookupError
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No se pudo eliminar la tarea.")
        
    return None
