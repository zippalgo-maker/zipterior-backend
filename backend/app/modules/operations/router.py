from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.common.dependencies import CurrentUser, CurrentAdmin
from app.core.database import get_db

router = APIRouter(tags=["operations"])

def company_id_for(session, user_id:int)->int:
    cid=session.execute(text("SELECT company_id FROM company_members WHERE user_id=:u AND status='active' ORDER BY CASE member_role WHEN 'owner' THEN 0 ELSE 1 END LIMIT 1"),{"u":user_id}).scalar()
    if not cid: raise HTTPException(403,"회원사 권한이 필요합니다.")
    return int(cid)

def rows(session, sql, params=None): return [dict(x) for x in session.execute(text(sql),params or {}).mappings().all()]

def one(session, sql, params=None):
    x=session.execute(text(sql),params or {}).mappings().one_or_none(); return dict(x) if x else None

class PartnerIn(BaseModel):
    name:str=Field(min_length=1,max_length=150); business_number:str|None=None
class UsageIn(BaseModel):
    partner_id:int; category:str=Field(min_length=1,max_length=80); contract_date:str; amount:int=Field(gt=0); memo:str|None=None; status:str="reviewing"
class UsageReview(BaseModel): status:str; memo:str|None=None
class PacketAdjust(BaseModel): amount:int; description:str=Field(min_length=2,max_length=300)
class PlanPatch(BaseModel): display_name:str|None=None; price:float|None=None; duration_days:int|None=None; is_active:bool|None=None

@router.get('/api/v1/company/operations')
def company_operations(current_user:CurrentUser, session:Session=Depends(get_db)):
    cid=company_id_for(session,current_user['id'])
    company=one(session,"""SELECT c.id,c.name,mp.plan_key,mp.display_name,cm.status membership_status,cm.expires_at,
      COALESCE(w.balance,0) packet_balance FROM companies c
      LEFT JOIN LATERAL (SELECT * FROM company_memberships WHERE company_id=c.id ORDER BY (status='active') DESC,started_at DESC LIMIT 1) cm ON true
      LEFT JOIN membership_plans mp ON mp.id=cm.plan_id LEFT JOIN company_packet_wallets w ON w.company_id=c.id WHERE c.id=:c""",{'c':cid})
    tx=rows(session,"SELECT id,transaction_type,amount,balance_after,reference_type,reference_id,description,created_at FROM packet_transactions WHERE company_id=:c ORDER BY id DESC LIMIT 100",{'c':cid})
    partners=rows(session,"SELECT id,name,business_number,status FROM partner_companies WHERE status='active' ORDER BY name")
    usages=rows(session,"""SELECT u.id,u.partner_id,p.name partner,u.category,u.contract_date,u.amount,u.status,u.memo,u.created_at
      FROM partner_usages u JOIN partner_companies p ON p.id=u.partner_id WHERE u.company_id=:c ORDER BY u.id DESC""",{'c':cid})
    best=rows(session,"SELECT id,complex_name,monthly_price,is_active FROM company_best_complexes WHERE company_id=:c ORDER BY id",{'c':cid})
    return {'company':company,'transactions':tx,'partners':partners,'partner_usages':usages,'best_complexes':best}

@router.post('/api/v1/company/partner-usages')
def create_usage(payload:UsageIn,current_user:CurrentUser,session:Session=Depends(get_db)):
    cid=company_id_for(session,current_user['id']); status='draft' if payload.status=='draft' else 'reviewing'
    row=one(session,"""INSERT INTO partner_usages(company_id,partner_id,category,contract_date,amount,status,memo,created_by)
      VALUES(:c,:p,:cat,CAST(:d AS date),:a,:s,:m,:u) RETURNING id,status,created_at""",{'c':cid,'p':payload.partner_id,'cat':payload.category,'d':payload.contract_date,'a':payload.amount,'s':status,'m':payload.memo,'u':current_user['id']}); session.commit(); return row

@router.get('/api/v1/admin/operations')
def admin_operations(current_admin:CurrentAdmin,session:Session=Depends(get_db)):
    plans=rows(session,"SELECT id,plan_key,display_name,price,duration_days,is_active FROM membership_plans ORDER BY id")
    memberships=rows(session,"""SELECT c.id company_id,c.name,mp.plan_key,mp.display_name,cm.status,cm.expires_at,COALESCE(w.balance,0) packet_balance
      FROM companies c LEFT JOIN LATERAL(SELECT * FROM company_memberships WHERE company_id=c.id ORDER BY (status='active') DESC,started_at DESC LIMIT 1) cm ON true
      LEFT JOIN membership_plans mp ON mp.id=cm.plan_id LEFT JOIN company_packet_wallets w ON w.company_id=c.id WHERE c.deleted_at IS NULL ORDER BY c.id DESC LIMIT 200""")
    tx=rows(session,"""SELECT t.id,c.name company,t.transaction_type,t.amount,t.balance_after,t.description,t.created_at FROM packet_transactions t JOIN companies c ON c.id=t.company_id ORDER BY t.id DESC LIMIT 200""")
    partners=rows(session,"SELECT id,name,business_number,status,created_at FROM partner_companies ORDER BY id DESC")
    usages=rows(session,"""SELECT u.id,c.name company,p.name partner,u.category,u.contract_date,u.amount,u.status,u.memo,u.created_at FROM partner_usages u JOIN companies c ON c.id=u.company_id JOIN partner_companies p ON p.id=u.partner_id ORDER BY u.id DESC LIMIT 200""")
    rules=rows(session,"SELECT id,complex_name,extra_packets,is_active FROM complex_packet_rules WHERE is_active ORDER BY complex_name")
    return {'plans':plans,'memberships':memberships,'transactions':tx,'partners':partners,'partner_usages':usages,'complex_packet_rules':rules}

@router.post('/api/v1/admin/partners')
def add_partner(payload:PartnerIn,current_admin:CurrentAdmin,session:Session=Depends(get_db)):
    r=one(session,"INSERT INTO partner_companies(name,business_number,created_by) VALUES(:n,:b,:u) RETURNING id,name,business_number,status",{'n':payload.name,'b':payload.business_number,'u':current_admin['id']});session.commit();return r

@router.delete('/api/v1/admin/partners/{partner_id}')
def delete_partner(partner_id:int,current_admin:CurrentAdmin,session:Session=Depends(get_db)):
    session.execute(text("UPDATE partner_companies SET status='inactive',updated_at=now() WHERE id=:i"),{'i':partner_id});session.commit();return {'ok':True}

@router.patch('/api/v1/admin/partner-usages/{usage_id}')
def review_usage(usage_id:int,payload:UsageReview,current_admin:CurrentAdmin,session:Session=Depends(get_db)):
    if payload.status not in {'approved','needs_revision','rejected'}: raise HTTPException(422,'허용되지 않은 상태입니다.')
    session.execute(text("UPDATE partner_usages SET status=:s,review_memo=:m,reviewed_by=:u,reviewed_at=now(),updated_at=now() WHERE id=:i"),{'s':payload.status,'m':payload.memo,'u':current_admin['id'],'i':usage_id});session.commit();return {'ok':True,'status':payload.status}

@router.post('/api/v1/admin/companies/{company_id}/packets/adjust')
def adjust_packet(company_id:int,payload:PacketAdjust,current_admin:CurrentAdmin,session:Session=Depends(get_db)):
    if payload.amount==0: raise HTTPException(422,'0은 처리할 수 없습니다.')
    session.execute(text("INSERT INTO company_packet_wallets(company_id,balance) VALUES(:c,0) ON CONFLICT(company_id) DO NOTHING"),{'c':company_id})
    bal=session.execute(text("UPDATE company_packet_wallets SET balance=balance+:a,updated_at=now() WHERE company_id=:c AND balance+:a>=0 RETURNING balance"),{'a':payload.amount,'c':company_id}).scalar()
    if bal is None: session.rollback(); raise HTTPException(409,'패킷 잔액이 부족합니다.')
    session.execute(text("INSERT INTO packet_transactions(company_id,transaction_type,amount,balance_after,description,created_by) VALUES(:c,'admin_adjust',:a,:b,:d,:u)"),{'c':company_id,'a':payload.amount,'b':bal,'d':payload.description,'u':current_admin['id']});session.commit();return {'company_id':company_id,'balance':bal}
class BestIn(BaseModel): complex_name:str=Field(min_length=1,max_length=200)
class RuleIn(BaseModel): complex_name:str=Field(min_length=1,max_length=200); extra_packets:int=Field(ge=0,le=100)

@router.post('/api/v1/company/best-complexes')
def add_best(payload:BestIn,current_user:CurrentUser,session:Session=Depends(get_db)):
    cid=company_id_for(session,current_user['id']); count=session.execute(text("SELECT count(*) FROM company_best_complexes WHERE company_id=:c AND is_active"),{'c':cid}).scalar() or 0
    price=0 if count<3 else 10000
    r=one(session,"INSERT INTO company_best_complexes(company_id,complex_name,monthly_price) VALUES(:c,:n,:p) ON CONFLICT(company_id,complex_name) DO UPDATE SET is_active=true,monthly_price=EXCLUDED.monthly_price RETURNING id,complex_name,monthly_price,is_active",{'c':cid,'n':payload.complex_name,'p':price});session.commit();return r

@router.delete('/api/v1/company/best-complexes/{best_id}')
def delete_best(best_id:int,current_user:CurrentUser,session:Session=Depends(get_db)):
    cid=company_id_for(session,current_user['id']);session.execute(text("UPDATE company_best_complexes SET is_active=false WHERE id=:i AND company_id=:c"),{'i':best_id,'c':cid});session.commit();return {'ok':True}

@router.post('/api/v1/admin/complex-packet-rules')
def add_rule(payload:RuleIn,current_admin:CurrentAdmin,session:Session=Depends(get_db)):
    r=one(session,"INSERT INTO complex_packet_rules(complex_name,extra_packets,updated_by) VALUES(:n,:e,:u) ON CONFLICT(complex_name) DO UPDATE SET extra_packets=EXCLUDED.extra_packets,is_active=true,updated_by=EXCLUDED.updated_by,updated_at=now() RETURNING id,complex_name,extra_packets,is_active",{'n':payload.complex_name,'e':payload.extra_packets,'u':current_admin['id']});session.commit();return r
