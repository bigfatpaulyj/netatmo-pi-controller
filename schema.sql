BEGIN TRANSACTION;
CREATE TABLE IF NOT EXISTS `netatmo` (
	`clientid`	TEXT NOT NULL,
	`redirect_url`	TEXT DEFAULT 'http://localhost:3000/postauth',
	`clientsecret`	TEXT NOT NULL,
	`token`	TEXT DEFAULT '',
	`refreshtoken`	TEXT DEFAULT '',
	`expiretime`	INTEGER DEFAULT 0,
	`desiredtemp`	INTEGER DEFAULT 18,
	`enabled`	INTEGER DEFAULT 1,
	PRIMARY KEY(`clientid`)
);
COMMIT;
