from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import FeedbackBlock
from schemas import BlockCreate, BlockOut

router = APIRouter()


@router.get("", response_model=list[BlockOut])
async def list_blocks(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(FeedbackBlock).order_by(FeedbackBlock.block_type, FeedbackBlock.value)
    )
    return result.scalars().all()


@router.post("", response_model=BlockOut, status_code=201)
async def create_block(payload: BlockCreate, db: AsyncSession = Depends(get_db)):
    if payload.block_type not in ("source", "topic"):
        raise HTTPException(status_code=422, detail="block_type must be 'source' or 'topic'")

    existing = await db.execute(
        select(FeedbackBlock).where(
            FeedbackBlock.block_type == payload.block_type,
            FeedbackBlock.value == payload.value,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Block already exists")

    block = FeedbackBlock(block_type=payload.block_type, value=payload.value)
    db.add(block)
    await db.commit()
    await db.refresh(block)
    return block


@router.delete("/{block_id}", status_code=204)
async def delete_block(block_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FeedbackBlock).where(FeedbackBlock.id == block_id))
    block = result.scalar_one_or_none()
    if not block:
        raise HTTPException(status_code=404, detail="Block not found")
    await db.delete(block)
    await db.commit()
