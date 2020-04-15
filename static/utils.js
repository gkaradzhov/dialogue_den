const JOIN_ROOM = 'JOIN_ROOM';
const CHAT_MESSAGE = 'CHAT_MESSAGE';
const LEAVE_ROOM = 'LEAVE_ROOM';
const FINISHED_ONBOARDING = 'FINISHED_ONBOARDING';
const WASON_INITIAL = 'WASON_INITIAL';
const WASON_GAME = 'WASON_GAME';
const WASON_AGREE = 'WASON_SUBMIT';
const WASON_FINISHED = 'WASON_FINISHED';

const USR_ONBOARDING = 'USR_ONBOARDING';
const USR_PLAYING = 'USR_PLAYING';
const USR_MODERATING = 'USR_MODERATING';


ROUTING_TIMER_STARTED = 'ROUTING_TIMER_STARTED'
ROUTING_TIMER_ELAPSED = 'ROUTING_TIMER_ELAPSED'

READY_TO_START = "READY_TO_START"
ROOM_PLAYING = "ROOM_PLAYING"

function split(val){
  return val.split( / \s*/ );
}

function extractLast(term) {
  return split(term).pop();
}

function boldMentions(str){
    var regex = new RegExp("@\\w*", 'gi');
    str = str.replace(regex, function(str) {return '<b>'+str+'</b>'});
    return str;
}

function start_timer(count_down, visualise, end_text, callback) {
    var now = new Date().getTime();
    // Find the distance between now and the count down date
    var distance = count_down - now;

    // Time calculations for days, hours, minutes and seconds

    var minutes = Math.floor((distance % (1000 * 60 * 60)) / (1000 * 60));
    var seconds = Math.floor((distance % (1000 * 60)) / 1000);

    if (visualise == true){
        if (distance < 0){
            $('#timer').text(end_text);
        }
        else{
            console.log(distance)
            $('#timer').text(minutes + " minutes " + seconds + " seconds");
        }
    }
    // If the count down is finished, write some text
    if (distance < 0) {
        callback();
    }
}


function get_card_selection(){
    var selection = [];
    $("input:checkbox").each(function(){
        selection.push({'value': $(this).val(), 'checked': $(this).is(":checked")});
    });

    return selection;
}


function activityWatcher(wakeup_callback, kick_callback){

    var secondsSinceLastActivity = 0;

    var kick_inactivity = (60 * 3);
    var notification_inactivity = (30 * 3)
    //Setup the setInterval method to run
    //every second. 1000 milliseconds = 1 second.

    setInterval(function(){
        secondsSinceLastActivity++;
        if(secondsSinceLastActivity > notification_inactivity){
            console.log('User has been inactive for more than ' + notification_inactivity + ' seconds');
            wakeup_callback();
            notification_inactivity = notification_inactivity * 2
        }

        if(secondsSinceLastActivity > kick_inactivity){
            console.log('User has been inactive for more than ' + kick_inactivity + ' seconds');
            //Redirect them to your logout.php page.
            kick_callback();
        }
    }, 1000);

    //The function that will be called whenever a user is active
    function activity(){
        //reset the secondsSinceLastActivity variable
        //back to 0
        secondsSinceLastActivity = 0;
        notification_inactivity = (30 * 3)
    }

    //An array of DOM events that should be interpreted as
    //user activity.
    var activityEvents = [
        'mousedown', 'mousemove', 'keydown',
        'scroll', 'touchstart'
    ];

    //add these events to the document.
    //register the activity function as the listener parameter.
    activityEvents.forEach(function(eventName) {
        document.addEventListener(eventName, activity, true);
    });
}