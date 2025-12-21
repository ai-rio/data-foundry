"""
Data Ingestion Flow using Prefect and dlt
This demonstrates the "Glue" integration between Prefect and dlt
"""

import asyncio
from datetime import datetime
from typing import Any

from dlt import pipeline
from dlt.destinations import postgres
from prefect import flow, get_run_logger, task

from src.core.config import settings


@task
def extract_data(data_source: str) -> list[dict[str, Any]]:
    """
    Extract data from source (simulated).
    In production, this would connect to various data sources.
    """
    logger = get_run_logger()
    logger.info(f"Extracting data from {data_source}")

    # Simulate data extraction
    sample_data = [
        {
            "id": 1,
            "name": "John Doe",
            "email": "john@example.com",
            "phone": "555-1234",
            "tenant_id": "tenant_001",
            "created_at": datetime.utcnow().isoformat(),
        },
        {
            "id": 2,
            "name": "Jane Smith",
            "email": "jane@example.com",
            "phone": "555-5678",
            "tenant_id": "tenant_001",
            "created_at": datetime.utcnow().isoformat(),
        },
        {
            "id": 3,
            "name": "Bob Johnson",
            "email": "bob@example.com",
            "phone": "555-9876",
            "tenant_id": "tenant_002",
            "created_at": datetime.utcnow().isoformat(),
        },
    ]

    logger.info(f"Extracted {len(sample_data)} records")
    return sample_data


@task
def apply_pii_redaction(data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Apply PII redaction using Microsoft Presidio.
    """
    logger = get_run_logger()
    logger.info("Applying PII redaction")

    try:
        # Try to import Presidio
        from presidio_analyzer import AnalyzerEngine
        from presidio_anonymizer import AnonymizerEngine

        analyzer = AnalyzerEngine()
        anonymizer = AnonymizerEngine()

        redacted_data = []
        for record in data:
            # Analyze and anonymize PII
            text_fields = ["name", "email", "phone"]
            redacted_record = record.copy()

            for field in text_fields:
                if field in record:
                    # Analyze the text
                    results = analyzer.analyze(text=record[field], language="en")

                    # Anonymize if PII detected
                    if results:
                        anonymized = anonymizer.anonymize(
                            text=record[field], analyzer_results=results
                        )
                        redacted_record[field] = anonymized.text

            redacted_data.append(redacted_record)

        logger.info(f"PII redaction applied to {len(redacted_data)} records")
        return redacted_data

    except ImportError:
        logger.warning("Presidio not installed, skipping PII redaction")
        return data


@task
async def apply_ai_labeling(data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Apply AI labeling using LiteLLM integrated AI Service.
    """
    logger = get_run_logger()
    logger.info("Applying AI labeling with LiteLLM integration")

    try:
        from src.services.ai_service import AIService, AIRequest
        import json

        # Initialize AI Service
        ai_service = AIService()
        await ai_service.initialize()

        labeled_data = []
        for record in data:
            try:
                # Create labeling prompt
                prompt = f"""
                Analyze this record and assign labels:
                Name: {record.get("name", "N/A")}
                Email: {record.get("email", "N/A")}
                Phone: {record.get("phone", "N/A")}

                Assign one of these categories:
                - 'high_value' (appears to be enterprise/corporate)
                - 'medium_value' (appears to be small business)
                - 'low_value' (appears to be personal)

                Also provide a confidence score (0-1).

                Return JSON: {{"category": "...", "confidence": ..., "reasoning": "..."}}
                """

                # Create AI request
                request = AIRequest(
                    prompt=prompt,
                    system_prompt="You are a data labeling expert.",
                    temperature=settings.OPENAI_TEMPERATURE,
                    max_tokens=200,
                    response_format="json",
                    tenant_id=record.get("tenant_id", "unknown"),
                    user_id=record.get("user_id"),
                    use_cache=True
                )

                # Call AI Service
                response = await ai_service.completion(request)

                # Parse response
                ai_result = json.loads(response.content)

                # Add AI results to record with enhanced metadata
                labeled_record = record.copy()
                labeled_record.update(
                    {
                        "ai_category": ai_result.get("category"),
                        "ai_confidence": ai_result.get("confidence"),
                        "ai_reasoning": ai_result.get("reasoning"),
                        "ai_model": response.model,
                        "ai_processed_at": datetime.utcnow().isoformat(),
                        "ai_request_id": response.request_id,
                        "ai_tokens_used": response.usage.total_tokens,
                        "ai_cost": str(response.cost),
                        "ai_processing_time_ms": response.response_time_ms,
                        "ai_fallback_used": response.fallback_used,
                        "ai_from_cache": response.from_cache
                    }
                )

                # Add provenance metadata
                provenance = {
                    "ai_service_version": "1.0.0",
                    "processing_pipeline": "ingestion_v2",
                    "model_provider": response.model.split("/")[0] if "/" in response.model else "openai",
                    "token_breakdown": {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens
                    },
                    "cost_breakdown": {
                        "currency": "USD",
                        "total_cost": str(response.cost)
                    }
                }
                labeled_record["provenance_metadata"] = json.dumps(provenance)

                # Add processing history
                processing_history = []
                if response.retry_count > 0:
                    processing_history.append({
                        "event": "model_retry",
                        "count": response.retry_count,
                        "timestamp": datetime.utcnow().isoformat()
                    })
                if response.fallback_used:
                    processing_history.append({
                        "event": "model_fallback",
                        "primary_model": settings.PRIMARY_MODEL,
                        "fallback_model": response.model,
                        "timestamp": datetime.utcnow().isoformat()
                    })
                if response.from_cache:
                    processing_history.append({
                        "event": "cache_hit",
                        "cache_key": response.completion_id,
                        "timestamp": response.cached_at.isoformat() if response.cached_at else datetime.utcnow().isoformat()
                    })

                labeled_record["processing_history"] = json.dumps(processing_history)

                labeled_data.append(labeled_record)

            except Exception as e:
                logger.error(f"AI labeling failed for record {record.get('id')}: {str(e)}")
                # Add error to record but continue processing
                error_record = record.copy()
                error_record["ai_error"] = str(e)
                error_record["ai_processed_at"] = datetime.utcnow().isoformat()
                labeled_data.append(error_record)

        logger.info(f"AI labeling applied to {len(labeled_data)} records")
        return labeled_data

    except Exception as e:
        logger.error(f"AI labeling service initialization failed: {str(e)}")
        # Fallback to original OpenAI if available
        logger.info("Attempting fallback to direct OpenAI API")

        try:
            from openai import OpenAI

            client = OpenAI(api_key=settings.secure_openai_api_key())

            labeled_data = []
            for record in data:
                prompt = f"""
                Analyze this record and assign labels:
                Name: {record.get("name", "N/A")}
                Email: {record.get("email", "N/A")}
                Phone: {record.get("phone", "N/A")}

                Assign one of these categories:
                - 'high_value' (appears to be enterprise/corporate)
                - 'medium_value' (appears to be small business)
                - 'low_value' (appears to be personal)

                Also provide a confidence score (0-1).

                Return JSON: {{"category": "...", "confidence": ..., "reasoning": "..."}}
                """

                response = client.chat.completions.create(
                    model=settings.OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": "You are a data labeling expert."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=settings.OPENAI_TEMPERATURE,
                    max_tokens=200,
                )

                ai_result = json.loads(response.choices[0].message.content)

                labeled_record = record.copy()
                labeled_record.update(
                    {
                        "ai_category": ai_result.get("category"),
                        "ai_confidence": ai_result.get("confidence"),
                        "ai_reasoning": ai_result.get("reasoning"),
                        "ai_model": settings.OPENAI_MODEL,
                        "ai_processed_at": datetime.utcnow().isoformat(),
                        "ai_fallback_method": "direct_openai"
                    }
                )

                labeled_data.append(labeled_record)

            logger.info(f"Fallback AI labeling applied to {len(labeled_data)} records")
            return labeled_data

        except Exception as fallback_error:
            logger.error(f"Fallback AI labeling also failed: {str(fallback_error)}")
            # Return data without AI labels but with error
            for record in data:
                record["ai_error"] = f"Primary: {str(e)}, Fallback: {str(fallback_error)}"
            return data


@task
def route_for_human_review(data: list[dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    """
    Route records based on confidence scores.
    Low confidence records go to Label Studio.
    """
    logger = get_run_logger()
    logger.info("Routing records for human review")

    auto_approved = []
    human_review = []

    for record in data:
        confidence = record.get("ai_confidence", 1.0)

        if confidence < settings.CONFIDENCE_THRESHOLD:
            human_review.append(record)
            logger.info(
                f"Record {record['id']} routed for human review (confidence: {confidence})"
            )
        else:
            auto_approved.append(record)
            logger.info(
                f"Record {record['id']} auto-approved (confidence: {confidence})"
            )

    logger.info(
        f"Auto-approved: {len(auto_approved)}, Human review: {len(human_review)}"
    )
    return auto_approved, human_review


@task
def send_to_label_studio(data: list[dict[str, Any]]) -> bool:
    """
    Send low-confidence records to Label Studio for human review.
    """
    logger = get_run_logger()
    logger.info(f"Sending {len(data)} records to Label Studio")

    try:
        from label_studio_sdk import Client

        # Connect to Label Studio
        ls = Client(
            url=settings.LABEL_STUDIO_URL, api_key=settings.secure_label_studio_api_key()
        )

        # Get or create project
        project = ls.get_project(settings.LABEL_STUDIO_PROJECT_ID)

        # Create tasks for human review
        tasks = []
        for record in data:
            task_data = {
                "data": {
                    "record_id": record["id"],
                    "original_data": record,
                    "ai_category": record.get("ai_category"),
                    "ai_confidence": record.get("ai_confidence"),
                    "ai_reasoning": record.get("ai_reasoning"),
                }
            }
            tasks.append(task_data)

        # Import tasks
        if tasks:
            project.import_tasks(tasks)
            logger.info(f"Successfully imported {len(tasks)} tasks to Label Studio")

        return True

    except Exception as e:
        logger.error(f"Failed to send to Label Studio: {str(e)}")
        return False


@task
def save_to_database(
    data: list[dict[str, Any]], table_name: str = "processed_data"
) -> bool:
    """
    Save processed data to PostgreSQL using dlt.
    """
    logger = get_run_logger()
    logger.info(f"Saving {len(data)} records to {table_name}")

    try:
        # Create dlt pipeline
        pipeline_obj = pipeline(
            pipeline_name="data_foundry_ingestion",
            destination=postgres(settings.DATABASE_URL_SYNC),
            dataset_name="public",
        )

        # Create a simple source
        def data_source():
            for record in data:
                yield record

        # Run pipeline
        load_info = pipeline_obj.run(data_source(), table_name=table_name)

        logger.info(f"Successfully saved {len(data)} records to database")
        logger.info(f"Load info: {load_info}")
        return True

    except Exception as e:
        logger.error(f"Failed to save to database: {str(e)}")
        return False


@flow(name="Data Foundry Ingestion Flow")
async def data_ingestion_flow(
    data_source: str = "sample_data",
    enable_ai_labeling: bool = True,
    enable_pii_redaction: bool = True,
    enable_human_review: bool = True,
):
    """
    Main ingestion flow that orchestrates the entire data processing pipeline.

    Args:
        data_source: Source of data to process
        enable_ai_labeling: Whether to apply AI labeling
        enable_pii_redaction: Whether to apply PII redaction
        enable_human_review: Whether to route low confidence for human review
    """
    logger = get_run_logger()
    logger.info("Starting Data Foundry Ingestion Flow")

    try:
        # Step 1: Extract data
        raw_data = await extract_data(data_source)

        # Step 2: Apply PII redaction
        if enable_pii_redaction:
            redacted_data = await apply_pii_redaction(raw_data)
        else:
            redacted_data = raw_data

        # Step 3: Apply AI labeling
        if enable_ai_labeling and (settings.secure_openai_api_key() or settings.PRIMARY_MODEL):
            labeled_data = await apply_ai_labeling(redacted_data)
        else:
            labeled_data = redacted_data
            logger.info("Skipping AI labeling - no API key configured")

        # Step 4: Route for human review
        if enable_human_review:
            auto_approved, human_review = await route_for_human_review(labeled_data)
        else:
            auto_approved = labeled_data
            human_review = []

        # Step 5: Send low confidence to Label Studio
        if human_review and settings.secure_label_studio_api_key():
            await send_to_label_studio(human_review)

        # Step 6: Save auto-approved data to database
        if auto_approved:
            await save_to_database(auto_approved, "auto_approved_data")

        # Step 7: Save human review queue to database
        if human_review:
            await save_to_database(human_review, "human_review_queue")

        logger.info("Data Ingestion Flow completed successfully")
        return {
            "total_records": len(raw_data),
            "auto_approved": len(auto_approved),
            "human_review": len(human_review),
            "success": True,
        }

    except Exception as e:
        logger.error(f"Data Ingestion Flow failed: {str(e)}")
        raise


if __name__ == "__main__":
    # Run the flow locally for testing
    asyncio.run(
        data_ingestion_flow(
            data_source="sample_data",
            enable_ai_labeling=False,  # Disable AI for testing without API keys
            enable_pii_redaction=False,  # Disable PII for testing
            enable_human_review=False,
        )
    )
