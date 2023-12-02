BEGIN TRANSACTION;
CREATE TABLE IF NOT EXISTS `netatmo` (
	`clientid`	TEXT NOT NULL,
	`redirect_url`	TEXT DEFAULT 'http://localhost/',
	`clientsecret`	TEXT,
	`token`	TEXT,
	`refreshtoken`	TEXT,
	`expiretime`	INTEGER NOT NULL,
	PRIMARY KEY(`clientid`)
);
COMMIT;
