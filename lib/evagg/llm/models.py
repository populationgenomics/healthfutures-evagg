"""Pydantic models for structured LLM responses in EvAgg pipeline."""

from pydantic import BaseModel, Field
from typing import Literal, List, Any


# Paper category models
class PaperCategoryResponse(BaseModel):
    """Response model for paper categorization."""
    category: Literal["genetic disease", "other"] = Field(
        description="Paper classification based on genetic disease criteria"
    )


# Content extraction models  
class VariantTypeResponse(BaseModel):
    """Response model for variant type classification."""
    variant_type: Literal[
        "missense", "frameshift", "stop gained", "splice donor", "splice acceptor", 
        "splice region", "start lost", "inframe deletion", "frameshift deletion", 
        "inframe insertion", "frameshift insertion", "structural", "synonymous", 
        "intron", "5' UTR", "3' UTR", "non-coding", "unknown"
    ] = Field(description="Type of genetic variant")


class ZygosityResponse(BaseModel):
    """Response model for zygosity determination."""
    zygosity: Literal["homozygous", "heterozygous", "compound heterozygous", "none"] = Field(
        description="Zygosity state of the variant"
    )


class VariantInheritanceResponse(BaseModel):
    """Response model for variant inheritance determination."""
    variant_inheritance: Literal["inherited", "de novo", "unknown"] = Field(
        description="How the variant was inherited"
    )


class StudyTypeResponse(BaseModel):
    """Response model for study type classification."""
    study_type: Literal["case report", "case series", "cohort analysis", "review", "other"] = Field(
        description="Type of study described in the paper"
    )


class FunctionalStudyResponse(BaseModel):
    """Response model for functional study identification."""
    functional_study: List[Literal["animal_model", "patient_cells_tissues", "engineered_cells", "none"]] = Field(
        description="Types of functional studies described in the paper"
    )


class PhenotypesResponse(BaseModel):
    """Response model for phenotype extraction."""
    phenotypes: List[str] = Field(
        description="List of clinical phenotypes found in the text",
        default_factory=list
    )


# Observation finder models
class SanityCheckResponse(BaseModel):
    """Response model for sanity check - whether text contains relevant variants."""
    relevant: bool = Field(
        description="Whether the text contains specific genetic variants for the gene of interest"
    )


class FindPatientsResponse(BaseModel):
    """Response model for patient identification."""
    patients: List[str] = Field(
        description="List of patient identifiers found in the text",
        default_factory=list
    )


class FindVariantsResponse(BaseModel):
    """Response model for variant identification."""
    variants: List[str] = Field(
        description="List of genetic variant descriptions found in the text",
        default_factory=list
    )


class GenomeBuildResponse(BaseModel):
    """Response model for genome build identification."""
    genome_build: str = Field(
        description="Genome build version identified in the text",
        default="unknown"
    )


class CheckPatientsResponse(BaseModel):
    """Response model for patient validation."""
    is_patient: bool = Field(
        description="Whether the identifier represents a valid patient in the text"
    )


class CheckVariantResponse(BaseModel):
    """Response model for variant-gene relationship validation."""
    related: bool = Field(
        description="Whether the variant is related to the gene of interest"
    )


class LinkEntitiesResponse(BaseModel):
    """Response model for linking patients to variants."""
    # Dynamic structure - will contain patient names as keys with variant lists as values
    model_config = {"extra": "allow"}  # Allow additional fields
    
    def __init__(self, **data: Any):
        # Handle the dynamic nature of this response
        super().__init__(**data)


class SplitPatientsResponse(BaseModel):
    """Response model for splitting patient lists."""
    patients: List[str] = Field(
        description="List of individual patient identifiers after splitting",
        default_factory=list
    )


class SplitVariantsResponse(BaseModel):
    """Response model for splitting variant descriptions."""
    variants: List[str] = Field(
        description="List of individual variant descriptions after splitting",
        default_factory=list
    )


# Phenotype processing models
class PhenotypeCandidatesResponse(BaseModel):
    """Response model for phenotype candidate matching."""
    match: str = Field(
        description="Best matching HPO term for the phenotype",
        default=""
    )


class PhenotypeSimplifyResponse(BaseModel):
    """Response model for phenotype simplification."""
    simplified: str = Field(
        description="Simplified version of the phenotype term",
        default=""
    )


class PhenotypeObservationResponse(BaseModel):
    """Response model for observation-specific phenotype extraction."""
    phenotypes: List[str] = Field(
        description="List of phenotypes associated with the specific observation",
        default_factory=list
    )


class PhenotypeAcronymsResponse(BaseModel):
    """Response model for phenotype acronym expansion."""
    phenotypes: List[str] = Field(
        description="List of phenotypes with expanded acronyms",
        default_factory=list
    )