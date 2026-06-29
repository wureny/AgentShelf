from __future__ import annotations

from dataclasses import dataclass, field


GEO_CATEGORIES = (
    "crawlability",
    "indexability",
    "structured_data",
    "content_extractability",
    "entity_consistency",
    "commerce_attributes",
    "trust",
    "ai_intent_coverage",
    "external_authority",
    "gtm",
)
VERTICALS = ("commerce", "creator_commerce", "artist_store", "local_service", "generic")
PROMPT_BUCKETS = (
    "brand",
    "category",
    "gift",
    "comparison",
    "alternative",
    "customization",
    "trust",
    "shipping",
    "price_value",
    "material_craft",
    "buyer_persona",
    "gtm",
)
SEVERITY_PENALTY = {"critical": 28, "high": 18, "medium": 10, "low": 5, "info": 0}


@dataclass
class GeoSkillConfig:
    targetUrl: str
    brandName: str | None = None
    storeName: str | None = None
    category: str | None = None
    market: list[str] = field(default_factory=list)
    language: str = "en"
    competitors: list[str] = field(default_factory=list)
    personas: list[str] = field(default_factory=list)
    useCases: list[str] = field(default_factory=list)
    keyProducts: list[str] = field(default_factory=list)
    maxPages: int = 1
    includePromptPanel: bool = True
    includePatchSuggestions: bool = True
    vertical: str = "commerce"
    outputFormat: str = "markdown"


@dataclass
class StoreProfile:
    brandName: str
    domain: str
    category: str
    vertical: str
    targetMarkets: list[str]
    targetLanguages: list[str]
    keyProducts: list[str]
    buyerPersonas: list[str]
    useCases: list[str]
    competitors: list[str]
    positioning: str
    uniqueClaims: list[str]


@dataclass
class GeoPage:
    url: str
    pageType: str
    title: str
    metaDescription: str | None
    h1: str | None
    headings: list[str]
    canonical: str | None
    textContent: str
    wordCount: int
    links: list[dict]
    images: list[dict]
    schemaTypes: list[str]
    productData: dict
    faqData: list[dict]
    extractedClaims: list[str]
    lastModified: str | None
    crawlStatus: dict


@dataclass
class GeoIssue:
    id: str
    severity: str
    category: str
    title: str
    description: str
    whyItMatters: str
    recommendation: str
    confidence: float
    pageUrl: str | None = None


@dataclass
class GeoOpportunity:
    id: str
    category: str
    title: str
    description: str
    expectedImpact: str
    effort: str
    recommendedAssetType: str
    relatedPrompts: list[str] = field(default_factory=list)


@dataclass
class GeoPrompt:
    id: str
    prompt: str
    language: str
    intentBucket: str
    commercialIntent: str
    priority: int
    targetAnswerRole: str


@dataclass
class GeoPatchSuggestion:
    id: str
    patchType: str
    title: str
    rationale: str
    suggestedCopy: str
    implementationNotes: str
    priority: str
    pageUrl: str | None = None
    suggestedSchema: dict | None = None


@dataclass
class GeoAuditResult:
    targetUrl: str
    generatedAt: str
    storeProfile: StoreProfile
    pages: list[GeoPage]
    overallScore: int
    categoryScores: dict[str, int]
    issues: list[GeoIssue]
    opportunities: list[GeoOpportunity]
    promptPanel: list[GeoPrompt]
    patchSuggestions: list[GeoPatchSuggestion]
    reportMarkdown: str
    rawMetadata: dict
