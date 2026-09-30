"""Add SIH26121 NWIS tables and PostGIS; historical migrations remain unchanged."""
from alembic import op

revision = "0018_nwis"
down_revision = "0017_accounts_recovery"
branch_labels = None
depends_on = None

def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA public")
    op.execute("""
CREATE TABLE nwis_wells (
	id VARCHAR(80) NOT NULL,
	name VARCHAR(120) NOT NULL,
	field VARCHAR(120) NOT NULL,
	latitude FLOAT,
	longitude FLOAT,
	location public.geography(Point,4326),
	operator VARCHAR(120),
	status VARCHAR(30) NOT NULL,
	spud_date DATE,
	total_depth_md FLOAT,
	current_md FLOAT,
	as_of TIMESTAMP WITH TIME ZONE,
	program JSONB,
	access_scope VARCHAR(20) NOT NULL,
	dataset_origin VARCHAR(100) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_nwis_wells PRIMARY KEY (id),
	CONSTRAINT ck_nwis_wells_coordinates CHECK (latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180)
)

""")
    op.execute('CREATE INDEX ix_nwis_wells_location ON nwis_wells USING gist (location)')
    op.execute("""
CREATE TABLE nwis_trajectory_points (
	well_id VARCHAR(80) NOT NULL,
	md FLOAT NOT NULL,
	tvd FLOAT,
	tvdss FLOAT,
	inclination FLOAT,
	azimuth FLOAT,
	northing FLOAT,
	easting FLOAT,
	source VARCHAR(200) NOT NULL,
	quality FLOAT NOT NULL,
	dataset_origin VARCHAR(100) NOT NULL,
	CONSTRAINT pk_nwis_trajectory_points PRIMARY KEY (well_id, md),
	CONSTRAINT ck_nwis_trajectory_points_trajectory_values CHECK (md >= 0 AND quality BETWEEN 0 AND 1),
	CONSTRAINT fk_nwis_trajectory_points_well_id_nwis_wells FOREIGN KEY(well_id) REFERENCES nwis_wells (id)
)

""")
    op.execute("""
CREATE TABLE nwis_formation_intervals (
	id VARCHAR(100) NOT NULL,
	well_id VARCHAR(80) NOT NULL,
	formation VARCHAR(100) NOT NULL,
	top_md FLOAT NOT NULL,
	bottom_md FLOAT NOT NULL,
	top_tvd FLOAT,
	bottom_tvd FLOAT,
	top_tvdss FLOAT,
	bottom_tvdss FLOAT,
	confidence FLOAT NOT NULL,
	source VARCHAR(200) NOT NULL,
	dataset_origin VARCHAR(100) NOT NULL,
	CONSTRAINT pk_nwis_formation_intervals PRIMARY KEY (id),
	CONSTRAINT ck_nwis_formation_intervals_formation_values CHECK (top_md >= 0 AND bottom_md > top_md AND confidence BETWEEN 0 AND 1),
	CONSTRAINT fk_nwis_formation_intervals_well_id_nwis_wells FOREIGN KEY(well_id) REFERENCES nwis_wells (id)
)

""")
    op.execute('CREATE INDEX ix_nwis_formation_intervals_formation ON nwis_formation_intervals (formation)')
    op.execute('CREATE INDEX ix_nwis_formation_intervals_well_id ON nwis_formation_intervals (well_id)')
    op.execute("""
CREATE TABLE nwis_drilling_reports (
	id VARCHAR(100) NOT NULL,
	well_id VARCHAR(80) NOT NULL,
	type VARCHAR(20) NOT NULL,
	report_date DATE,
	file_hash VARCHAR(64) NOT NULL,
	extraction_status VARCHAR(30) NOT NULL,
	parser_version VARCHAR(50) NOT NULL,
	dataset_origin VARCHAR(100) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_nwis_drilling_reports PRIMARY KEY (id),
	CONSTRAINT uq_nwis_drilling_reports_well_id UNIQUE (well_id, file_hash),
	CONSTRAINT ck_nwis_drilling_reports_report_type CHECK (type IN ('WCR','DDR','incident','program')),
	CONSTRAINT fk_nwis_drilling_reports_well_id_nwis_wells FOREIGN KEY(well_id) REFERENCES nwis_wells (id)
)

""")
    op.execute('CREATE INDEX ix_nwis_drilling_reports_well_id ON nwis_drilling_reports (well_id)')
    op.execute("""
CREATE TABLE nwis_drilling_events (
	id VARCHAR(100) NOT NULL,
	well_id VARCHAR(80) NOT NULL,
	event_type VARCHAR(40) NOT NULL,
	start_depth_md FLOAT,
	end_depth_md FLOAT,
	tvd FLOAT,
	tvdss FLOAT,
	formation VARCHAR(100),
	severity VARCHAR(30) NOT NULL,
	observation TEXT NOT NULL,
	cause TEXT,
	mitigation TEXT,
	outcome TEXT,
	npt_hours FLOAT,
	confidence FLOAT NOT NULL,
	source_report_id VARCHAR(100) NOT NULL,
	source_page INTEGER NOT NULL,
	source_span JSONB,
	raw_phrase TEXT NOT NULL,
	verification_state VARCHAR(30) NOT NULL,
	dataset_origin VARCHAR(100) NOT NULL,
	CONSTRAINT pk_nwis_drilling_events PRIMARY KEY (id),
	CONSTRAINT ck_nwis_drilling_events_event_values CHECK (confidence BETWEEN 0 AND 1 AND source_page > 0 AND (npt_hours IS NULL OR npt_hours >= 0) AND (start_depth_md IS NULL OR start_depth_md >= 0) AND (end_depth_md IS NULL OR end_depth_md >= start_depth_md)),
	CONSTRAINT fk_nwis_drilling_events_well_id_nwis_wells FOREIGN KEY(well_id) REFERENCES nwis_wells (id),
	CONSTRAINT fk_nwis_drilling_events_source_report_id_nwis_drilling_reports FOREIGN KEY(source_report_id) REFERENCES nwis_drilling_reports (id)
)

""")
    op.execute('CREATE INDEX ix_nwis_drilling_events_event_type ON nwis_drilling_events (event_type)')
    op.execute('CREATE INDEX ix_nwis_drilling_events_formation ON nwis_drilling_events (formation)')
    op.execute('CREATE INDEX ix_nwis_drilling_events_well_id ON nwis_drilling_events (well_id)')
    op.execute("""
CREATE TABLE nwis_telemetry_samples (
	well_id VARCHAR(80) NOT NULL,
	timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
	channel VARCHAR(50) NOT NULL,
	md FLOAT NOT NULL,
	tvd FLOAT,
	value FLOAT,
	unit VARCHAR(30) NOT NULL,
	quality VARCHAR(30) NOT NULL,
	dataset_origin VARCHAR(100) NOT NULL,
	CONSTRAINT pk_nwis_telemetry_samples PRIMARY KEY (well_id, timestamp, channel),
	CONSTRAINT fk_nwis_telemetry_samples_well_id_nwis_wells FOREIGN KEY(well_id) REFERENCES nwis_wells (id)
)

""")
    op.execute("""
CREATE TABLE nwis_offset_matches (
	id VARCHAR(64) NOT NULL,
	active_well_id VARCHAR(80) NOT NULL,
	offset_well_id VARCHAR(80) NOT NULL,
	geographic_score FLOAT NOT NULL,
	formation_score FLOAT,
	depth_score FLOAT,
	trajectory_score FLOAT,
	program_score FLOAT,
	data_quality_score FLOAT NOT NULL,
	total_score FLOAT NOT NULL,
	algorithm_version VARCHAR(50) NOT NULL,
	dataset_origin VARCHAR(100) NOT NULL,
	CONSTRAINT pk_nwis_offset_matches PRIMARY KEY (id),
	CONSTRAINT fk_nwis_offset_matches_active_well_id_nwis_wells FOREIGN KEY(active_well_id) REFERENCES nwis_wells (id),
	CONSTRAINT fk_nwis_offset_matches_offset_well_id_nwis_wells FOREIGN KEY(offset_well_id) REFERENCES nwis_wells (id)
)

""")
    op.execute("""
CREATE TABLE nwis_risk_assessments (
	id VARCHAR(64) NOT NULL,
	well_id VARCHAR(80) NOT NULL,
	as_of TIMESTAMP WITH TIME ZONE NOT NULL,
	current_md FLOAT,
	formation VARCHAR(100),
	lookahead_m INTEGER NOT NULL,
	hazard_type VARCHAR(40) NOT NULL,
	probability FLOAT,
	confidence FLOAT NOT NULL,
	trend VARCHAR(30) NOT NULL,
	model_version VARCHAR(50) NOT NULL,
	snapshot JSONB NOT NULL,
	dataset_origin VARCHAR(100) NOT NULL,
	CONSTRAINT pk_nwis_risk_assessments PRIMARY KEY (id),
	CONSTRAINT ck_nwis_risk_assessments_risk_values CHECK ((probability IS NULL OR probability BETWEEN 0 AND 1) AND confidence BETWEEN 0 AND 1),
	CONSTRAINT fk_nwis_risk_assessments_well_id_nwis_wells FOREIGN KEY(well_id) REFERENCES nwis_wells (id)
)

""")
    op.execute('CREATE INDEX ix_nwis_risk_assessments_well_id ON nwis_risk_assessments (well_id)')
    op.execute("""
CREATE TABLE nwis_risk_evidence (
	assessment_id VARCHAR(64) NOT NULL,
	drilling_event_id VARCHAR(100) NOT NULL,
	evidence_chunk_id VARCHAR(100),
	offset_well_id VARCHAR(80) NOT NULL,
	contribution FLOAT NOT NULL,
	reason TEXT NOT NULL,
	dataset_origin VARCHAR(100) NOT NULL,
	CONSTRAINT pk_nwis_risk_evidence PRIMARY KEY (assessment_id, drilling_event_id),
	CONSTRAINT fk_nwis_risk_evidence_assessment_id_nwis_risk_assessments FOREIGN KEY(assessment_id) REFERENCES nwis_risk_assessments (id),
	CONSTRAINT fk_nwis_risk_evidence_drilling_event_id_nwis_drilling_events FOREIGN KEY(drilling_event_id) REFERENCES nwis_drilling_events (id),
	CONSTRAINT fk_nwis_risk_evidence_offset_well_id_nwis_wells FOREIGN KEY(offset_well_id) REFERENCES nwis_wells (id)
)

""")
    op.execute("""
CREATE TABLE nwis_advisories (
	id VARCHAR(64) NOT NULL,
	assessment_id VARCHAR(64) NOT NULL,
	text TEXT NOT NULL,
	status VARCHAR(30) NOT NULL,
	reviewer UUID,
	reviewed_at TIMESTAMP WITH TIME ZONE,
	feedback TEXT,
	model_route VARCHAR(80) NOT NULL,
	dataset_origin VARCHAR(100) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_nwis_advisories PRIMARY KEY (id),
	CONSTRAINT fk_nwis_advisories_assessment_id_nwis_risk_assessments FOREIGN KEY(assessment_id) REFERENCES nwis_risk_assessments (id),
	CONSTRAINT fk_nwis_advisories_reviewer_users FOREIGN KEY(reviewer) REFERENCES users (id)
)

""")
    op.execute("""
CREATE TABLE nwis_alert_states (
	well_id VARCHAR(80) NOT NULL,
	hazard VARCHAR(40) NOT NULL,
	interval INTEGER NOT NULL,
	consecutive INTEGER NOT NULL,
	active BOOLEAN NOT NULL,
	last_as_of TIMESTAMP WITH TIME ZONE,
	last_alert_at TIMESTAMP WITH TIME ZONE,
	CONSTRAINT pk_nwis_alert_states PRIMARY KEY (well_id, hazard, interval),
	CONSTRAINT fk_nwis_alert_states_well_id_nwis_wells FOREIGN KEY(well_id) REFERENCES nwis_wells (id)
)

""")
    op.execute("""
CREATE TABLE nwis_terms_acceptances (
	user_id UUID NOT NULL,
	version VARCHAR(50) NOT NULL,
	accepted_at TIMESTAMP WITH TIME ZONE NOT NULL,
	CONSTRAINT pk_nwis_terms_acceptances PRIMARY KEY (user_id, version),
	CONSTRAINT fk_nwis_terms_acceptances_user_id_users FOREIGN KEY(user_id) REFERENCES users (id)
)

""")
    op.execute("""CREATE FUNCTION nwis_sync_location() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      NEW.location := CASE WHEN NEW.latitude IS NULL OR NEW.longitude IS NULL THEN NULL
        ELSE public.ST_SetSRID(public.ST_MakePoint(NEW.longitude, NEW.latitude),4326)::public.geography END;
      RETURN NEW;
    END $$""")
    op.execute("CREATE TRIGGER nwis_location BEFORE INSERT OR UPDATE ON nwis_wells FOR EACH ROW EXECUTE FUNCTION nwis_sync_location()")

def downgrade():
    op.execute("DROP TRIGGER nwis_location ON nwis_wells")
    op.execute("DROP FUNCTION nwis_sync_location()")
    op.drop_table('nwis_terms_acceptances')
    op.drop_table('nwis_alert_states')
    op.drop_table('nwis_advisories')
    op.drop_table('nwis_risk_evidence')
    op.drop_table('nwis_risk_assessments')
    op.drop_table('nwis_offset_matches')
    op.drop_table('nwis_telemetry_samples')
    op.drop_table('nwis_drilling_events')
    op.drop_table('nwis_drilling_reports')
    op.drop_table('nwis_formation_intervals')
    op.drop_table('nwis_trajectory_points')
    op.drop_table('nwis_wells')
