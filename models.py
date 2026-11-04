from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey
from sqlalchemy.orm import relationship
from database import Base
from pgvector.sqlalchemy import Vector

# ==========================================
# 1. UNIVERSITY & PROGRAM TABLES (SQL)
# ==========================================
class University(Base):
    __tablename__ = "universities"

    id = Column(Integer, primary_key=True, index=True)
    official_name = Column(String, index=True, nullable=False, unique=True)
    city = Column(String, index=True)
    federal_state = Column(String, index=True)
    institution_type = Column(String) 
    ranking_system = Column(String, default="QS")
    rank = Column(Integer, nullable=True) 
    rank_year = Column(Integer, default=2027)
    official_url = Column(String)
    source_url = Column(String)
    
    programs = relationship("Program", back_populates="university")

class Program(Base):
    __tablename__ = "programs"

    id = Column(Integer, primary_key=True, index=True)
    university_id = Column(Integer, ForeignKey("universities.id"))
    title = Column(String, index=True)
    degree_type = Column(String) 
    field_of_study = Column(String, index=True)
    language = Column(String) 
    tuition_fee_eur = Column(Float, nullable=True) 
    semester_contribution_eur = Column(Float, nullable=True)
    duration_semesters = Column(Integer, nullable=True)
    official_program_url = Column(String)
    
    university = relationship("University", back_populates="programs")

# ==========================================
# 2. POLICY DOCUMENT TABLE (RAG Vector DB)
# ==========================================
class PolicyDocument(Base):
    __tablename__ = "policy_documents"

    id = Column(Integer, primary_key=True, index=True)
    topic = Column(String, index=True)
    source_file = Column(String) 
    chunk_text = Column(Text, nullable=False)
    embedding = Column(Vector(3072)) 

# ==========================================
# 3. STUDENT PROFILE TABLE (CV Data)
# ==========================================
class StudentProfile(Base):
    __tablename__ = "student_profiles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    profile_json = Column(Text, nullable=False)