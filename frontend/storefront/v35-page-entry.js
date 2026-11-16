import {publicPageDestination} from './v35-pages.js';
const destination=publicPageDestination(location.href);
if(destination)location.replace(destination);
